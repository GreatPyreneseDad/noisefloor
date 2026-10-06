import argparse
import sys
import time

START = time.time()


def status_line():
    return f"ok  uptime {time.time() - START:.1f}s"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="svc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    args = ap.parse_args(argv)
    if args.cmd == "status":
        print(status_line())
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
