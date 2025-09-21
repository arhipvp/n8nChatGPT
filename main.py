import sys
from argparse import ArgumentParser

from dotenv import load_dotenv

from runtime import ROOT, run


def parse_args(argv=None):
    parser = ArgumentParser(description="Запуск MCP-сервера и ngrok-туннеля")
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Проверить загрузку конфигурации без запуска процессов",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    load_dotenv(ROOT / ".env")

    if args.no_run:
        return 0

    return run()


if __name__ == "__main__":
    sys.exit(main())
