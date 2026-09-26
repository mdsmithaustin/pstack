# Withdraw cash

As an account holder, I want to withdraw cash from my current account, so that I have money to spend.

Notes from refinement:

- Every current account has an overdraft limit of £100.
- The smallest withdrawal is £10. A request for less than £10 is refused with "The minimum withdrawal is £10".
- A withdrawal that leaves the balance above -£100 is paid out, and the balance goes down by the amount withdrawn.
- A withdrawal that would take the balance below -£100 is refused. The balance does not change, and the customer sees "Insufficient funds".
