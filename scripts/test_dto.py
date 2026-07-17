"""Demo: what happens with bad data."""

from pydantic import ValidationError
from app.schemas.auth import RegisterRequest

tests = [
    {"username": "ab", "password": "12345"},           # too short
    {"username": "mustafa"},                            # missing password
    {"username": 123, "password": "secret123"},         # wrong type
    {"username": "mustafa", "password": "secret123", "extra": "field"},  # extra field
]

for t in tests:
    try:
        result = RegisterRequest(**t)
        print(f"OK:     {t}")
    except ValidationError as e:
        print(f"REJECT: {t}")
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            print(f"        {loc}: {err['msg']}")
    print()
