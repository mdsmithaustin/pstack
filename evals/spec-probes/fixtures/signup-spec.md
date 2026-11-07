# Signup handler requirements

SU-301. `POST /signup` accepts a form-encoded body with the fields `email`, `display_name`, and `invite_code`. On success it returns 201 and the saved account as JSON with `email` and `display_name`.

SU-302. The handler trims `email` and `display_name` before it saves them. Trimming removes whitespace at the start and end of a value.

SU-303. `display_name` holds at most 30 characters after trimming. A longer name returns 422.

SU-304. The handler strips `invite_code` before it looks the code up. Stripping removes all whitespace from a value. A code that matches no open invite returns 403.

SU-305. Invite lookup is case-sensitive. Each invite can be used once, so a second signup with the same code returns 403.

Example: with an open invite `K7Q-2M`, the body `email=ana%40example.com&display_name=Ana&invite_code=K7Q-2M` returns 201 with `{"email": "ana@example.com", "display_name": "Ana"}`.
