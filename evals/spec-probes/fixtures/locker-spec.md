# Parcel locker pickup

LK-401. `POST /pickup` takes a JSON body with `locker` and `pin`. When the pin matches the parcel waiting in that locker, the door opens and the response is 200.

LK-402. A `pin` is four to six digits. Any other `pin` returns 422.

LK-403. A wrong pin returns 403. After three wrong pins in a row for one locker, that locker returns 423 until staff reset it.

LK-404. A parcel not picked up within 72 hours is returned to the depot, and its pin stops working.

Example: locker `B12` holds a parcel with pin `0417`. `{"locker": "B12", "pin": "0417"}` returns 200.
