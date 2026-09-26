The story states three rules. It never says what happens when a withdrawal lands exactly on -£100, so that example stays a question.

<file path="docs/withdrawal-acceptance.md">
# Withdraw cash: acceptance criteria

## Rule: the smallest withdrawal is £10

Given my balance is £200
When I ask to withdraw £5
Then the withdrawal is refused with "The minimum withdrawal is £10"
And my balance is still £200

## Rule: a withdrawal that leaves the balance above -£100 is paid out

Given my balance is £50
When I withdraw £40
Then I receive £40
And my balance is £10

Given my balance is -£20
When I withdraw £60
Then I receive £60
And my balance is -£80

## Rule: a withdrawal that would take the balance below -£100 is refused

Given my balance is £50
When I withdraw £200
Then the withdrawal is refused with "Insufficient funds"
And my balance is still £50

## Open questions

Given my balance is £50
When I withdraw £150
Then ? The story does not say whether a withdrawal that leaves the balance at exactly -£100 is paid out or refused.
</file>
