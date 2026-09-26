<file path="docs/withdrawal-acceptance.md">
# Withdraw cash: acceptance criteria

Scenario: a withdrawal below the minimum is refused
  Given my balance is £200
  When I ask to withdraw £5
  Then the withdrawal is refused with "The minimum withdrawal is £10"

Scenario: a withdrawal within the overdraft is paid out
  Given my balance is £50
  When I withdraw £40
  Then I receive £40
  And my balance is £10

Scenario: a withdrawal that reaches the overdraft limit is paid out
  Given my balance is £50
  When I withdraw £150
  Then I receive £150
  And my balance is -£100

Scenario: a withdrawal past the overdraft limit is refused
  Given my balance is £50
  When I withdraw £200
  Then the withdrawal is refused with "Insufficient funds"
</file>
