from stage3.budget import BudgetManager


budget = BudgetManager(total=100)

assert budget.allow_narrative() is True
assert budget.safety_checks_enabled is True

assert budget.consume(79) is True

assert budget.allow_narrative() is True
assert budget.safety_checks_enabled is True

assert budget.consume(1) is True

assert budget.allow_narrative() is False
assert budget.safety_checks_enabled is True

print("Budget degradation test: PASS")