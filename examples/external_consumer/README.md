# NeuraHive External Consumer Example

This example represents a completely unrelated project consuming NeuraHive as an SDK.

The example intentionally uses only the public `neurahive` namespace. It does not import the legacy `agentfactory` package, FastAPI, SQLAlchemy, Studio, or platform state.

## Goal

Prove the core architectural promise:

```text
Consumer project
      ↓
   neurahive
      ↓
 injected provider
      ↓
 independent runtime
```

The example uses a fake provider so it can run without API credentials or external services.

## Run

From the repository root:

```bash
python examples/external_consumer/app.py
```

Expected output:

```text
handled: hello from an unrelated project
```

A real consumer can replace the fake provider with its own `ModelProvider` implementation without changing the NeuraHive core.
