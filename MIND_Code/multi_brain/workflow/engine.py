"""Workflow Execution Engine: Orchestrates multi-brain execution according to a DAG."""

from __future__ import annotations

import collections
import concurrent.futures
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

from multi_brain.contracts import (
    Provenance,
    TaskNode,
    TaskPlan,
    TaskRequest,
    TaskResult,
    TaskStatus,
    WorkflowProgress,
    WorkflowResult,
)
from multi_brain.registries.brain_registry import BrainRegistry
from multi_brain.workflow.context import TaskContext

logger = logging.getLogger("mind.multi_brain.workflow_engine")


class WorkflowEngine:
    """
    Executes multi-brain workflows according to DAG dependencies.
    Supports bounded parallel execution of independent tasks, topological ordering,
    context propagation, bounded retries, and comprehensive error handling.
    """

    def __init__(
        self,
        brain_registry: BrainRegistry,
        max_parallel_workers: int = 4,
    ) -> None:
        self.brain_registry = brain_registry
        self.max_parallel_workers = max_parallel_workers

    def validate_plan(self, plan: TaskPlan) -> None:
        """
        Validates the DAG plan structure:
        - Ensures all task IDs are unique.
        - Checks that all referenced dependencies exist.
        - Detects cycles using Kahn's algorithm or DFS.
        """
        task_map = {t.task_id: t for t in plan.tasks}
        if len(task_map) != len(plan.tasks):
            raise ValueError("Duplicate task_id detected in plan tasks.")

        # Check dependency references
        for task in plan.tasks:
            for dep in task.dependencies:
                if dep not in task_map:
                    raise ValueError(f"Task '{task.task_id}' references non-existent dependency '{dep}'.")

        # Cycle detection via Kahn's algorithm
        in_degree: Dict[str, int] = {t.task_id: len(t.dependencies) for t in plan.tasks}
        adj_list: Dict[str, List[str]] = collections.defaultdict(list)
        for task in plan.tasks:
            for dep in task.dependencies:
                adj_list[dep].append(task.task_id)

        queue = collections.deque([t_id for t_id, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            curr = queue.popleft()
            visited_count += 1
            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(plan.tasks):
            raise ValueError("Circular dependency (cycle) detected in workflow execution plan.")

    def execute_plan(
        self,
        plan: TaskPlan,
        context: Optional[TaskContext] = None,
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> WorkflowResult:
        """
        Executes a validated DAG plan end to end.
        Independent tasks run in parallel up to max_parallel_workers.
        Dependent tasks wait for dependencies to succeed and receive their outputs.
        Supports live progress emissions and cooperative task cancellation.
        """
        start_time = time.time()
        self.validate_plan(plan)

        ctx = context or TaskContext(
            original_goal=plan.original_request,
            workflow_id=plan.plan_id,
        )

        task_map = {t.task_id: t for t in plan.tasks}
        task_results: Dict[str, TaskResult] = {}
        completed_tasks: Set[str] = set()
        failed_tasks: Set[str] = set()
        skipped_tasks: Set[str] = set()
        cancelled: bool = False
        total_tasks = max(1, len(plan.tasks))

        def _get_current_task_statuses() -> Dict[str, Dict[str, Any]]:
            statuses = {}
            for t in plan.tasks:
                if t.task_id in task_results:
                    r = task_results[t.task_id]
                    statuses[t.task_id] = {
                        "title": t.title,
                        "brain_id": t.brain_id,
                        "status": r.status.value,
                        "is_success": r.is_success,
                        "error": r.error,
                        "execution_time_seconds": r.execution_time_seconds,
                    }
                elif any(active_id == t.task_id for active_id in active_futures.values()):
                    statuses[t.task_id] = {
                        "title": t.title,
                        "brain_id": t.brain_id,
                        "status": TaskStatus.RUNNING.value,
                        "is_success": False,
                        "error": None,
                        "execution_time_seconds": 0.0,
                    }
                else:
                    statuses[t.task_id] = {
                        "title": t.title,
                        "brain_id": t.brain_id,
                        "status": TaskStatus.PENDING.value,
                        "is_success": False,
                        "error": None,
                        "execution_time_seconds": 0.0,
                    }
            return statuses

        def _emit_progress(node: TaskNode, status: TaskStatus, pct: float, msg: str, art: Optional[Dict[str, Any]] = None, err: Optional[str] = None):
            if progress_callback:
                try:
                    cancellation_reason = getattr(cancellation_token, "reason", None) if cancelled else None
                    progress_callback(
                        WorkflowProgress(
                            workflow_id=plan.plan_id,
                            active_task_id=node.task_id,
                            active_task_title=node.title,
                            brain_id=node.brain_id,
                            status=status,
                            progress_pct=pct,
                            message=msg,
                            completed_tasks=len(completed_tasks),
                            total_tasks=total_tasks,
                            current_artifact=art,
                            error=err,
                            task_statuses=_get_current_task_statuses(),
                            is_cancelled=cancelled,
                            cancellation_reason=cancellation_reason,
                        )
                    )
                except Exception as cb_err:
                    logger.debug(f"Progress callback error: {cb_err}")

        # Build in-degree and dependents map
        in_degree: Dict[str, int] = {t.task_id: len(t.dependencies) for t in plan.tasks}
        dependents: Dict[str, List[str]] = collections.defaultdict(list)
        for task in plan.tasks:
            for dep in task.dependencies:
                dependents[dep].append(task.task_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            active_futures: Dict[concurrent.futures.Future, str] = {}

            def _submit_ready_tasks() -> None:
                nonlocal cancelled
                if cancellation_token and hasattr(cancellation_token, "is_set") and cancellation_token.is_set():
                    cancelled = True
                    return

                for t_id, deg in list(in_degree.items()):
                    if deg == 0 and t_id not in completed_tasks and t_id not in failed_tasks and t_id not in skipped_tasks:
                        if not any(active_id == t_id for active_id in active_futures.values()):
                            task_node = task_map[t_id]
                            # Check if any dependency failed or was skipped
                            dep_failed = any(dep in failed_tasks or dep in skipped_tasks for dep in task_node.dependencies)
                            if dep_failed:
                                skip_res = TaskResult(
                                    task_id=t_id,
                                    status=TaskStatus.SKIPPED,
                                    output=None,
                                    error=f"Dependency failed or was skipped: {task_node.dependencies}",
                                    provenance=Provenance(brain_id=task_node.brain_id, confidence=0.0),
                                )
                                task_results[t_id] = skip_res
                                skipped_tasks.add(t_id)
                                ctx.store_result(t_id, skip_res)
                                _emit_progress(task_node, TaskStatus.SKIPPED, len(completed_tasks)/total_tasks, f"Skipped: {task_node.title}")
                                for dep_child in dependents[t_id]:
                                    in_degree[dep_child] -= 1
                            else:
                                _emit_progress(task_node, TaskStatus.RUNNING, (len(completed_tasks)+0.1)/total_tasks, f"Starting {task_node.title} via {task_node.brain_id}...")
                                fut = executor.submit(self._execute_single_task_with_retry, task_node, ctx)
                                active_futures[fut] = t_id

            # Initial submission
            _submit_ready_tasks()

            while active_futures:
                if cancellation_token and hasattr(cancellation_token, "is_set") and cancellation_token.is_set():
                    cancelled = True
                    for fut in active_futures:
                        fut.cancel()
                    break

                done, _ = concurrent.futures.wait(
                    active_futures.keys(),
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

                for fut in done:
                    t_id = active_futures.pop(fut)
                    task_node = task_map[t_id]
                    try:
                        res: TaskResult = fut.result()
                    except Exception as e:
                        res = TaskResult(
                            task_id=t_id,
                            status=TaskStatus.FAILED,
                            output=None,
                            error=f"Unhandled engine error: {e}",
                            provenance=Provenance(brain_id=task_node.brain_id, confidence=0.0),
                        )

                    task_results[t_id] = res
                    ctx.store_result(t_id, res)

                    first_art = res.artifacts[0] if res.artifacts else None
                    if res.is_success:
                        completed_tasks.add(t_id)
                        _emit_progress(task_node, TaskStatus.COMPLETED, len(completed_tasks)/total_tasks, f"Completed: {task_node.title}", art=first_art)
                        for child_id in dependents[t_id]:
                            in_degree[child_id] -= 1
                        try:
                            from multi_brain.voice.authority import CentralVoiceNotificationAuthority
                            from multi_brain.voice.contracts import NotificationPriority
                            CentralVoiceNotificationAuthority.get_instance().report_task_completion(
                                task_id=t_id,
                                source_id=task_node.brain_id,
                                summary=task_node.title,
                                workflow_id=plan.plan_id,
                                result_reference=str(first_art.get("path")) if first_art else None,
                                priority=NotificationPriority.NORMAL,
                            )
                        except Exception as ev_err:
                            logger.debug(f"Silent completion event skipped: {ev_err}")
                    else:
                        failed_tasks.add(t_id)
                        _emit_progress(task_node, TaskStatus.FAILED, len(completed_tasks)/total_tasks, f"Failed: {task_node.title}", err=res.error)
                        for child_id in dependents[t_id]:
                            in_degree[child_id] -= 1
                        try:
                            from multi_brain.voice.authority import CentralVoiceNotificationAuthority
                            from multi_brain.voice.contracts import NotificationPriority
                            CentralVoiceNotificationAuthority.get_instance().report_task_failure(
                                task_id=t_id,
                                source_id=task_node.brain_id,
                                summary=task_node.title,
                                error_details={"message": str(res.error)},
                                workflow_id=plan.plan_id,
                                priority=NotificationPriority.HIGH,
                            )
                        except Exception as ev_err:
                            logger.debug(f"Silent failure event skipped: {ev_err}")

                _submit_ready_tasks()

        # Handle cancellation of remaining tasks
        if cancelled:
            for t_id, task_node in task_map.items():
                if t_id not in task_results:
                    task_results[t_id] = TaskResult(
                        task_id=t_id,
                        status=TaskStatus.CANCELLED,
                        output=None,
                        error="Execution cancelled by user request.",
                        provenance=Provenance(brain_id=task_node.brain_id, confidence=0.0),
                    )

        # Determine overall workflow status
        if cancelled:
            overall_status = TaskStatus.CANCELLED
        elif failed_tasks:
            overall_status = TaskStatus.FAILED
        else:
            overall_status = TaskStatus.COMPLETED

        # Build final aggregated output
        final_output = self._aggregate_final_output(plan, task_results)

        # Collect partial artifacts if cancelled or failed
        partial_artifacts: List[Dict[str, Any]] = []
        if overall_status in (TaskStatus.CANCELLED, TaskStatus.FAILED):
            for t_id, r in task_results.items():
                if r.artifacts:
                    for a in r.artifacts:
                        art_dict = dict(a)
                        art_dict["is_partial"] = True
                        partial_artifacts.append(art_dict)

        # Verification summary
        v_summary = {
            "total_tasks": total_tasks,
            "completed": len(completed_tasks),
            "failed": len(failed_tasks),
            "skipped": len(skipped_tasks),
            "verified_tasks": sum(1 for r in task_results.values() if r.verification),
        }

        cancellation_reason = getattr(cancellation_token, "reason", None) if cancelled else None

        # Authoritative Workflow Voice Notification
        try:
            from multi_brain.voice.authority import CentralVoiceNotificationAuthority
            from multi_brain.voice.contracts import NotificationPriority
            va = CentralVoiceNotificationAuthority.get_instance()
            if overall_status == TaskStatus.COMPLETED:
                va.report_workflow_completion(
                    workflow_id=plan.plan_id,
                    summary="Your development workflow has been completed successfully. Everything is ready.",
                    priority=NotificationPriority.NORMAL,
                )
            elif overall_status == TaskStatus.FAILED:
                va.report_workflow_completion(
                    workflow_id=plan.plan_id,
                    summary="Your workflow encountered errors during execution. Diagnostics have been recorded.",
                    priority=NotificationPriority.HIGH,
                )
        except Exception as wf_ev_err:
            logger.debug(f"Workflow completion voice notification skipped: {wf_ev_err}")

        return WorkflowResult(
            workflow_id=plan.plan_id,
            status=overall_status,
            plan=plan,
            task_results=task_results,
            final_output=final_output,
            execution_duration=time.time() - start_time,
            audit_trail=ctx.provenance_ledger,
            cancellation_reason=cancellation_reason,
            partial_artifacts=partial_artifacts,
            verification_summary=v_summary,
        )

    def _execute_single_task_with_retry(
        self,
        node: TaskNode,
        ctx: TaskContext,
    ) -> TaskResult:
        """Executes a single task node with bounded retries."""
        brain = self.brain_registry.get(node.brain_id)
        if not brain:
            return TaskResult(
                task_id=node.task_id,
                status=TaskStatus.FAILED,
                output=None,
                error=f"Specialist brain '{node.brain_id}' is not registered.",
                provenance=Provenance(brain_id=node.brain_id, confidence=0.0),
            )

        # Build scoped context slice from dependencies
        context_slice = ctx.get_slice_for_task(node.task_id, node.dependencies)

        # Merge input data
        merged_inputs = dict(node.inputs)
        # Add dependency outputs directly
        merged_inputs.update(context_slice.get("dependency_outputs", {}))

        attempts = 0
        last_result: Optional[TaskResult] = None

        while attempts <= node.max_retries:
            attempts += 1
            req = TaskRequest(
                task_id=node.task_id,
                user_goal=node.description,
                input_data=merged_inputs,
                parameters={"title": node.title, "expected_output_type": node.expected_output_type},
                context_slice=context_slice,
                required_capabilities=node.required_capabilities,
                timeout_seconds=node.timeout_seconds,
            )

            result = brain.execute(req)
            last_result = result

            if result.is_success:
                return result

            logger.warning(
                f"Task '{node.task_id}' attempt {attempts}/{node.max_retries + 1} failed: {result.error}"
            )

        return last_result or TaskResult(
            task_id=node.task_id,
            status=TaskStatus.FAILED,
            output=None,
            error="Task failed after maximum retries.",
            provenance=Provenance(brain_id=node.brain_id, confidence=0.0),
        )

    def _aggregate_final_output(
        self,
        plan: TaskPlan,
        results: Dict[str, TaskResult],
    ) -> Dict[str, Any]:
        """Collects deliverables, artifacts, and summary from completed leaf nodes."""
        outputs = {}
        all_artifacts = []
        for t_id, res in results.items():
            if res.is_success:
                outputs[t_id] = res.output
                if res.artifacts:
                    all_artifacts.extend(res.artifacts)

        return {
            "plan_id": plan.plan_id,
            "tasks_executed": len(results),
            "tasks_successful": sum(1 for r in results.values() if r.is_success),
            "task_outputs": outputs,
            "artifacts": all_artifacts,
        }
