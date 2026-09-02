# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project Standard

This project is a production-oriented tennis data platform intended to become a real commercial app. All development, design, architecture, and code quality should follow mature product standards, with emphasis on stability, maintainability, extensibility, data consistency, and user experience.

Do not treat this as a toy demo or temporary prototype unless the user explicitly says so.

## Project Shape

This repository is organized as a multi-surface tennis data system:

* `backend/`: Backend API, PostgreSQL schemas, users, and task management.
* `cv/`: Computer vision pipeline for video analysis, tracking, events, analytics, persistence, and sample data.
* `web/`: Web dashboard and admin console.
* `app/`: React Native / Expo mobile app.
* `shared/`: Shared API schemas, data schemas, constants, and cross-platform contracts.
* `docs/`: Project documentation, especially tennis data and database design.
* `scripts/`: Startup, deployment, migration, and data-processing scripts.

PostgreSQL is the project's only database for application runtime, CV
persistence, local development, and supported database tests. Do not add an
embedded-file database fallback. The only documented exception is the
one-time, read-only historical import procedure in
`POSTGRES_MIGRATION_GUIDE.md`.

## Work Process

Before making code changes, first understand the requirement, analyze the affected scope, and propose a clear plan.

For unclear, broad, or cross-module tasks, ask for clarification before implementation. Do not guess the user's intent or expand the task scope on your own.

For simple and clearly bounded tasks, keep the change small and proceed according to the existing local patterns.

## Scope Control

Only modify files that are relevant to the requested task. Do not modify code unrelated to the current task.

Avoid unrelated refactors, formatting changes, file deletions, dependency changes, or behavior changes. If a larger change is necessary, explain why before doing it.

## Data Consistency

The global data definition is maintained in:

`docs/data/tennis_global_data_dictionary.md`

Field names, meanings, units, enum values, and data structures should stay consistent across the database, backend API, App, Web, CV pipeline, analytics scripts, and shared schemas.

When adding or changing data fields, update the global data dictionary and check affected upstream and downstream consumers.

When changing database design, also provide executable migration scripts or clear steps so other collaborators can apply the change and run the project successfully.

Treat `shared/` schemas and constants as cross-application contracts. Update all relevant consumers together when changing shared data structures.

## Local Documentation

Read the nearest `README.md` before changing a subsystem.

The `cv/` tree may contain focused README or `CLAUDE.md` files that document local behavior, data formats, and constraints. Consult them when working in those paths.

Keep documentation updates concise and close to the behavior they describe.

## Comments

Comments should help humans and AI agents understand, search, and maintain the code. Avoid meaningless comments that only repeat what the code says.

Important files, modules, and functions should explain:

* What they are responsible for
* Main inputs and outputs
* Why the design is this way
* Important boundary conditions or assumptions

Complex logic should include comments explaining the design idea.

## Product Quality

Build features from the perspective of real users:

* Is the flow easy to understand?
* Is the operation simple?
* Are loading, failure, empty, and abnormal states handled?
* Are error messages clear?
* Is the implementation maintainable and extensible?

Do not only aim for “it runs.” Aim for stable, clear, and shippable.

## Decoupling

Keep different features and subsystems independent where possible. Maintain clear boundaries between backend, CV, Web, App, shared contracts, and scripts.

Avoid mixing unrelated responsibilities in the same module.


## Product Specification

The product and feature specification is maintained in:

`docs/PRODUCT_FEATURE_SPEC.md`

This document focuses on what the product does, including its features, user-facing behavior, page/module design, user flows, and important product decisions.

When implementing features, keep this document updated with confirmed requirements, feature behavior, page/module descriptions, important product decisions, and meaningful changes made during development.

If the user's request changes an existing feature, update the relevant part of `docs/PRODUCT_FEATURE_SPEC.md` instead of only changing the code.

Keep the specification concise, factual, and aligned with the actual product behavior. Do not invent product requirements that the user has not confirmed.

Keep `docs/ui/UI_NAMING_REGISTRY.md` in sync with product changes. When adding or changing visible pages, sections, dialogs, drawers, sheets, or key reusable components, register their stable UI names there.

## Encoding

Use UTF-8 for all source code, configuration files, documentation, database scripts, and text assets. Do not save files with GBK, ANSI, or other legacy encodings.
