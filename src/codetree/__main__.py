import argparse
from .server import run

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Path to repo root")
    args = parser.parse_args()
    run(args.root)

if __name__ == "__main__":
    main()
