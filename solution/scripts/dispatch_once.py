from datetime import datetime

from app.services.provider import provider
from app.services.dispatcher import dispatch_once


def main():
    clock = provider.get_clock()
    now = datetime.fromisoformat(clock["sim_now"])

    print("Provider simulated time:", now.isoformat())

    result = dispatch_once(now)

    if result is None:
        print("No eligible lead available.")
    else:
        print("Dispatch result:", result)


if __name__ == "__main__":
    main()
