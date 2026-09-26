Feature: Shipping
  Shipping is free from 50.00 after discounts, and a flat 4.99 below that.

  Scenario: An order below the threshold pays flat shipping
    Given a cart with 2 "mug" at 12.00
    When the cart is quoted
    Then shipping is 4.99
    And the total is 28.99

  Scenario: An order of exactly 50.00 ships free
    Given a cart with 1 "kettle" at 50.00
    When the cart is quoted
    Then shipping is 0.00
    And the total is 50.00
