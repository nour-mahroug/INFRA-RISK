from __future__ import annotations
import argparse, inspect, json, logging, os, time
from collections import Counter
from pathlib import Path
from typing import Any

from .config import load_config

LOG = logging.getLogger(__name__)
JOB_PREFIX = "infra-risk"


def _login():
    """Log in to HyP3 with the Earthdata credentials stored in .env."""
    from dotenv import load_dotenv
    load_dotenv()
    user, pwd = os.getenv("ASF_USERNAME"), os.getenv("ASF_PASSWORD")
    if not user or not pwd:
        raise SystemExit("Put ASF_USERNAME and ASF_PASSWORD (your NASA Earthdata login) in the .env file.")
    import hyp3_sdk
    return hyp3_sdk.HyP3(username=user, password=pwd)


def find_scenes(cfg: dict[str, Any], start: str, end: str, direction: str) -> list[dict[str, Any]]:
    """Search Sentinel-1 IW SLC scenes that fully cover the area of interest."""
    import asf_search as asf
    from shapely.geometry import box, shape
    west, south, east, north = cfg["aoi"]["bbox"]
    aoi = box(west, south, east, north)
    results = asf.search(
        platform=[asf.PLATFORM.SENTINEL1], processingLevel=[asf.PRODUCT_TYPE.SLC],
        beamMode=[asf.BEAMMODE.IW], intersectsWith=aoi.wkt, start=start, end=end,
        flightDirection=direction)
    scenes = []
    for item in results:
        props = item.properties
        scenes.append({"name": props["sceneName"], "start": str(props["startTime"]),
                       "track": props.get("pathNumber"),
                       "covers": bool(shape(item.geometry).contains(aoi))})
    LOG.info("ASF returned %d scenes (%d fully cover the area)", len(scenes),
             sum(s["covers"] for s in scenes))
    return scenes


def plan_jobs(scenes: list[dict[str, Any]], months: int) -> dict[str, Any]:
    """Choose one track, one scene per month, and pair each scene with its next two."""
    covering = [s for s in scenes if s["covers"]]
    if not covering:
        raise SystemExit("No single scene covers the whole area in this period. Try other dates or direction.")
    tracks = Counter(s["track"] for s in covering)
    track = tracks.most_common(1)[0][0]
    chosen, seen_months = [], set()
    for scene in sorted((s for s in covering if s["track"] == track), key=lambda s: s["start"]):
        month = scene["start"][:7]
        if month not in seen_months:
            seen_months.add(month)
            chosen.append(scene)
        if len(chosen) >= months:
            break
    pairs = []
    for i, first in enumerate(chosen):
        for second in chosen[i + 1:i + 3]:
            pairs.append((first, second))
    return {"track": track, "scenes": chosen, "pairs": pairs}


def _kwargs_supported(func, **wanted) -> dict[str, Any]:
    """Keep only keyword arguments that this hyp3_sdk version accepts (and say what was dropped)."""
    params = inspect.signature(func).parameters
    kept = {k: v for k, v in wanted.items() if k in params}
    dropped = sorted(set(wanted) - set(kept))
    if dropped:
        LOG.warning("This hyp3_sdk version does not accept: %s", ", ".join(dropped))
    return kept


def _print_plan(plan: dict[str, Any]) -> None:
    print(f"\nTrack (relative orbit): {plan['track']}")
    print(f"Scenes selected: {len(plan['scenes'])}")
    for s in plan["scenes"]:
        print(f"  {s['start'][:10]}  {s['name']}")
    print(f"Interferogram pairs: {len(plan['pairs'])}")
    for a, b in plan["pairs"]:
        print(f"  {a['start'][:10]} -> {b['start'][:10]}")


def _jobs_file(cfg: dict[str, Any]) -> Path:
    return Path(cfg["paths"]["raw"]) / "hyp3_jobs.json"


def cmd_submit(cfg: dict[str, Any], plan: dict[str, Any]) -> None:
    hyp3 = _login()
    try:
        print("HyP3 credits remaining:", hyp3.check_credits())
    except Exception:  # not critical
        LOG.warning("Could not read remaining credits; check them on the HyP3 website.")
    _print_plan(plan)
    if input(f"\nSubmit {len(plan['pairs'])} HyP3 InSAR jobs now? Type YES to continue: ").strip() != "YES":
        raise SystemExit("Cancelled, nothing submitted.")
    extra = _kwargs_supported(hyp3.submit_insar_job, looks="20x4", include_displacement_maps=True,
                              apply_water_mask=True)
    saved = []
    for a, b in plan["pairs"]:
        name = f"{JOB_PREFIX}-{a['start'][:10]}-{b['start'][:10]}"
        batch = hyp3.submit_insar_job(a["name"], b["name"], name=name, **extra)
        job = batch.jobs[0] if hasattr(batch, "jobs") else batch
        saved.append({"job_id": job.job_id, "name": name, "granule1": a["name"], "granule2": b["name"]})
        print("submitted", name)
    path = _jobs_file(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text()) if path.exists() else []
    path.write_text(json.dumps(existing + saved, indent=2), encoding="utf-8")
    print(f"\nJob IDs saved to {path}. Run 'python -m src.hyp3_jobs status' later.")


def _load_jobs(cfg: dict[str, Any], hyp3) -> list[Any]:
    path = _jobs_file(cfg)
    if not path.exists():
        raise SystemExit(f"{path} not found: submit jobs first.")
    return [hyp3.get_job_by_id(item["job_id"]) for item in json.loads(path.read_text())]


def cmd_status(cfg: dict[str, Any]) -> None:
    jobs = _load_jobs(cfg, _login())
    print(dict(Counter(job.status_code for job in jobs)))


def cmd_download(cfg: dict[str, Any]) -> None:
    jobs = _load_jobs(cfg, _login())
    out = Path(cfg["paths"]["raw"])
    out.mkdir(parents=True, exist_ok=True)
    done = [j for j in jobs if j.status_code == "SUCCEEDED"]
    print(f"{len(done)}/{len(jobs)} jobs finished; downloading to {out} ...")
    for job in done:
        if (out / f"{job.name}.done").exists():
            continue
        ok = False
        for attempt in range(1, 8):
            # No .done marker means any file of this job is incomplete: remove it, then start again.
            for f in (job.files or []):
                part = out / f["filename"]
                if part.exists():
                    part.unlink()
            try:
                job.download_files(out)
                ok = True
                break
            except Exception as exc:
                print(f"  attempt {attempt}/7 failed for {job.name}: {type(exc).__name__}; retrying...")
                time.sleep(5)
        if not ok:
            for f in (job.files or []):
                part = out / f["filename"]
                if part.exists():
                    part.unlink()
            print("GAVE UP on", job.name, "- rerun the download later")
            continue
        (out / f"{job.name}.done").write_text("ok")
        print("downloaded", job.name)
    failed = [j.name for j in jobs if j.status_code == "FAILED"]
    if failed:
        print("FAILED jobs (ignore or resubmit):", failed)


def main() -> None:
    parser = argparse.ArgumentParser(description="ASF HyP3 job helper for INFRA-RISK")
    parser.add_argument("command", choices=["plan", "submit", "status", "download"])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--start", default="2024-07-01")
    parser.add_argument("--end", default="2025-06-30")
    parser.add_argument("--months", type=int, default=12, help="number of monthly scenes (default 12)")
    parser.add_argument("--direction", default=None, help="ASCENDING or DESCENDING (default: config.yaml)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    if args.command in ("plan", "submit"):
        direction = args.direction or cfg["insar"]["orbit_direction"]
        plan = plan_jobs(find_scenes(cfg, args.start, args.end, direction), args.months)
        if args.command == "plan":
            _print_plan(plan)
        else:
            cmd_submit(cfg, plan)
    elif args.command == "status":
        cmd_status(cfg)
    else:
        cmd_download(cfg)


if __name__ == "__main__":
    main()