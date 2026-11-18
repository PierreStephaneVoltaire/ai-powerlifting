# ADR-0009: Supplements use their own store

## Decision

Store `supplements` and `supplement_phases` in the `if-supplements` DynamoDB
table. Use the Athlete as `pk` and the exact Program version sort key as `sk`.
Program reads hydrate those fields from this table, falling back to the legacy
Program item when a supplements row has not been migrated. Program writes keep
the fields out of `if-health` after the supplements write succeeds. Existing
Program API shapes and operations stay unchanged.

## Consequences

Supplement history remains isolated by Program version and follows the same
Block scoping rules as before. Existing records can be migrated independently;
unmigrated records remain readable during rollout.
