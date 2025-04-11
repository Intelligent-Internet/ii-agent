from datetime import datetime
import json
import logging
import os
import subprocess
import time
from pathlib import Path
import huggingface_hub

from rich.console import Console

from utils.docker_utils import stop_container


def get_dataset_name(dataset: str) -> str:
    """Get the dataset name for the specified dataset."""
    return {
        "verified": "princeton-nlp/SWE-bench_Verified",
        "full": "princeton-nlp/SWE-bench",
        "lite": "princeton-nlp/SWE-bench_Lite",
    }[dataset]


def run_evaluation(
    predictions_file: Path,
    dataset: str,
    run_id: str,
    swebench_venv_path: Path,
    console: Console,
    num_processes: int = 1,
    capture_output: bool = False,
):
    """Run the SWE-bench evaluation on the predictions file."""

    et = datetime.now()
    env = os.environ.copy()
    instance_id = json.loads(predictions_file.read_text())[0].get("instance_id")
    report_dir = predictions_file.parent
    cmd = [
        swebench_venv_path.as_posix(),
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset,
        "--predictions_path",
        predictions_file.name,
        "--run_id",
        run_id,
        "--max_workers",
        str(num_processes),
        "--report_dir",
        report_dir.as_posix(),
        "--cache_level",
        "instance",
        "--namespace",
        "swebench",
        "--instance_image_tag",
        "latest",
    ]
    logging.info(f"Running {' '.join(cmd)} in {predictions_file.parent}")
    max_tries = 5
    retry_backoff = 10  # seconds
    tries = 1
    while True:
        if instance_id is not None:
            stop_container(f"sweb.eval.{instance_id}.swe_work")
        try:
            evaluation: subprocess.CompletedProcess = subprocess.run(
                cmd,
                env=env,
                cwd=predictions_file.parent,
                capture_output=capture_output,
            )
        except huggingface_hub.errors.HfHubHTTPError as e:
            logging.warning(
                f"Failed to run evaluation for {instance_id}: {e}. Retrying."
            )
            continue
        tries += 1
        want_retry = False
        eval_log_dir = predictions_file.parent / "logs"
        if eval_log_dir.exists():
            eval_log_file = list(eval_log_dir.rglob("run_instance.log"))
            if eval_log_file:
                eval_log_file = eval_log_file[0]
                eval_report_file = (
                    predictions_file.parent / f"augment-agent.{run_id}.json"
                )
                if not eval_report_file.exists():
                    # Eval ran, but not prediction.  Retry.
                    logging.warning(
                        f"Failed to find report file {eval_report_file} for {instance_id}"
                    )
                    want_retry = True
                if "ERROR - Error creating container" in eval_log_file.read_text():
                    # Docker startup failed.  Retry.
                    logging.warning(
                        f"Failed to run evaluation for {instance_id} (rc {evaluation.returncode})"
                    )
                    want_retry = True
            else:
                logging.warning(
                    f"No eval log for {instance_id} (rc {evaluation.returncode})"
                )
                want_retry = True

        if not want_retry or tries > max_tries:
            break
        else:
            logging.info(f"Retrying evaluation for {instance_id}")
            if eval_log_dir.exists():
                eval_log_dir.rename(
                    eval_log_dir.parent / f"{eval_log_dir.name}_{tries}"
                )
            time.sleep(retry_backoff)
            retry_backoff *= 2
    logging.warning(
        f"Evaluations completed for {predictions_file.name} in {datetime.now() - et} ({(datetime.now() - et).total_seconds():.2f}s) rc {evaluation.returncode}"
    )
    return evaluation
