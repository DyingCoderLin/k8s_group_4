def handler(event: dict, context: dict) -> dict:
    return {"result": "hello {}{}!".format(event, context)}