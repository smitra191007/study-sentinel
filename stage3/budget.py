from dataclasses import dataclass


@dataclass
class BudgetManager:
    """
    Controls the single budget shared across the complete
    surveillance period.
    """

    total: float
    used: float = 0.0

    # At 80% usage, narrative work is disabled.
    degradation_threshold: float = 0.80

    narrative_enabled: bool = True

    def consume(
        self,
        amount: float,
    ) -> bool:
        """
        Consume budget.

        Returns True when the requested amount was consumed.
        Returns False when insufficient budget remains.
        """

        amount = float(amount)

        if amount < 0:
            raise ValueError(
                "Budget consumption cannot be negative."
            )

        if self.used + amount > self.total:
            return False

        self.used += amount

        self._update_degradation()

        return True

    def _update_degradation(self) -> None:
        """
        Disable narrative work once 80% of the total budget
        has been consumed.
        """

        if self.total <= 0:
            self.narrative_enabled = False
            return

        usage_ratio = self.used / self.total

        if usage_ratio >= self.degradation_threshold:
            self.narrative_enabled = False

    @property
    def usage_ratio(self) -> float:
        if self.total <= 0:
            return 1.0

        return self.used / self.total

    @property
    def remaining(self) -> float:
        return max(
            0.0,
            self.total - self.used,
        )

    @property
    def safety_checks_enabled(self) -> bool:
        """
        Deterministic safety checks continue even after
        narrative work is disabled.
        """

        return True

    def allow_narrative(self) -> bool:
        return self.narrative_enabled

    def status(self) -> dict:
        return {
            "total": self.total,
            "used": self.used,
            "remaining": self.remaining,
            "usage_ratio": self.usage_ratio,
            "narrative_enabled": self.narrative_enabled,
            "safety_checks_enabled": self.safety_checks_enabled,
        }
