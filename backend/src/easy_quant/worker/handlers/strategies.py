from easy_quant.worker.registry import JobHandlerRegistry


def register_strategy_handlers(registry: JobHandlerRegistry) -> None:
    registry.register("strategy.validate", lambda job: {"validated": bool(job.payload)})
    registry.register("strategy.run", lambda job: {"run": job.payload})
