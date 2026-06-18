"""Population rings (design doc §5.5 / §8 market): estimated population within 25/50/100/150
miles of a acquisition, auto-pulled when a property is entered and overridable by the underwriter.

The demographics provider is an unresolved decision (ADR-0009); the factory returns None
until configured, so rings stay empty (or operator-entered) rather than fabricated.
"""
