import json
from redis_client import get_redis

def send_reply(r, reply_to, request_id, service, status, result=None, error=None):
    msg = {
        "request_id": request_id,
        "service": service,
        "status": status,
        "result": result,
        "error": error,
    }
    r.lpush(reply_to, json.dumps(msg))
    r.expire(reply_to, 30)

def start_import_adapter(queue_name, service_name, handler):
    r = get_redis()
    print(f"[{service_name}] listening on {queue_name}")

    while True:
        item = r.brpop(queue_name, timeout=0)
        if not item:
            continue

        _, raw = item
        job = json.loads(raw)

        request_id = job["request_id"]
        reply_to = job["reply_to"]
        payload = job["payload"]

        try:
            result = handler(payload)
            send_reply(
                r,
                reply_to,
                request_id,
                service_name,
                "success",
                result=result,
            )
        except Exception as exc:
            send_reply(
                r,
                reply_to,
                request_id,
                service_name,
                "error",
                error=str(exc),
            )