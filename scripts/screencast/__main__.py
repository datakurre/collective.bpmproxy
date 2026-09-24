"""`python -m screencast` -- see scripts/screencast/driver.py for what each
subcommand actually does; this module is argument parsing only."""

from pathlib import Path
from screencast import driver
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m screencast")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a story")
    run_parser.add_argument("story")
    run_parser.add_argument("--task", default=None, help="Run only this task (by name)")
    run_parser.add_argument("--no-record", action="store_true")
    run_parser.add_argument("--take", default=None, help="Take directory")
    run_parser.add_argument("--headed", action="store_true")

    probe_parser = subparsers.add_parser("probe", help="Run one keyword live")
    probe_parser.add_argument("keyword")
    probe_parser.add_argument("args", nargs="*")
    probe_parser.add_argument("--resource", default=None)
    probe_parser.add_argument("--take", default=".")
    probe_parser.add_argument("--record", action="store_true")
    probe_parser.add_argument("--headed", action="store_true")
    probe_parser.add_argument("--repl", action="store_true")

    keywords_parser = subparsers.add_parser(
        "keywords", help="List a resource's keywords"
    )
    keywords_parser.add_argument("resource")

    check_parser = subparsers.add_parser(
        "check", help="Dry-run a story without a browser"
    )
    check_parser.add_argument("story")
    check_parser.add_argument("--take", default=None)

    log_parser = subparsers.add_parser("log", help="Render log.html for a take")
    log_parser.add_argument("take")

    compose_parser = subparsers.add_parser("compose", help="Compose a take's timeline")
    compose_parser.add_argument("take")
    compose_parser.add_argument("--output", default=None)

    verify_parser = subparsers.add_parser("verify", help="Verify a composed take")
    verify_parser.add_argument("take")
    verify_parser.add_argument("--output", default=None, help="Composed video path")
    verify_parser.add_argument("--contact-sheet", default=None)
    verify_parser.add_argument("--rows", type=int, default=6)
    verify_parser.add_argument("--cols", type=int, default=5)

    args = parser.parse_args(argv)

    if args.command == "run":
        code, _ = driver.run(
            args.story,
            task=args.task,
            record=not args.no_record,
            take_dir=args.take,
            headless=not args.headed,
        )
        return code

    if args.command == "probe":
        if args.repl:
            driver.repl(
                args.resource,
                take_dir=args.take,
                record=args.record,
                headless=not args.headed,
            )
            return 0
        return driver.probe(
            args.resource,
            args.keyword,
            args.args,
            take_dir=args.take,
            record=args.record,
            headless=not args.headed,
        )

    if args.command == "keywords":
        print(driver.keywords(args.resource))
        return 0

    if args.command == "check":
        errors = driver.check(args.story, take_dir=args.take)
        if errors:
            print("\n".join(errors))
            return 1
        print(f"{args.story}: OK")
        return 0

    if args.command == "log":
        path = driver.render_log(args.take)
        print(f"Wrote {path}")
        return 0

    if args.command == "compose":
        from screencast.compose import compose

        path = compose(args.take, output=args.output)
        print(f"Wrote {path}")
        return 0

    if args.command == "verify":
        from screencast.verify import verify
        import json

        report = verify(
            args.take,
            output_video=args.output,
            contact_sheet=args.contact_sheet,
            rows=args.rows,
            cols=args.cols,
        )
        report_path = Path(args.take) / "report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        print(f"Report: {report_path}")
        return 0 if report["ok"] else 1

    parser.error(f"Unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
