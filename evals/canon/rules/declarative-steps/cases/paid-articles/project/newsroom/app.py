import json

ARTICLES = {
    "town-budget": {"title": "Town budget passes", "paid": False},
    "harbor-deal": {"title": "Inside the harbor deal", "paid": True},
}
SESSIONS = {"tok-free-1": "free", "tok-paid-1": "paid"}
STATUS_TEXT = {200: "200 OK", 402: "402 Payment Required", 404: "404 Not Found"}


def plan_for(environ):
    header = environ.get("HTTP_AUTHORIZATION", "")
    token = header.removeprefix("Bearer ").strip()
    return SESSIONS.get(token, "anonymous")


def app(environ, start_response):
    slug = environ.get("PATH_INFO", "").removeprefix("/articles/")
    article = ARTICLES.get(slug)
    if environ.get("REQUEST_METHOD") != "GET" or article is None:
        status, payload = 404, {"error": "not found"}
    elif article["paid"] and plan_for(environ) != "paid":
        status, payload = 402, {"error": "subscription required"}
    else:
        status, payload = 200, {"title": article["title"]}
    start_response(STATUS_TEXT[status], [("Content-Type", "application/json")])
    return [json.dumps(payload).encode()]
