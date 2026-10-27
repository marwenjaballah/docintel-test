# Changelog

## Task 1: DB sessions and auth (tickets 2 & 5)
- Killed the global DB session in app/db.py and added a get_db() dependency, so each request gets its own.
- Switched the key check to secrets.compare_digest. The old compare was open to timing attacks.
- GET /results/{rid} wasn’t behind auth. It is now.
- /extract, /match and /results/{rid} all use get_db.
- Uploads are saved under a UUID instead of the user’s filename, so no more path traversal.
- Stopped logging raw CV text. It was leaking PII.
- /match now has real MatchRequest and MatchResult types.
- Errors were returning {"error": ...} with a 200. They’re proper 404/500s now.
- Added tests for authed results, the 404 and /match validation.
