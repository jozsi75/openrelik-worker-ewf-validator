import json
import os
import subprocess
import tempfile
from pathlib import Path

from celery import signals
from celery.utils.log import get_task_logger
from openrelik_worker_common.file_utils import create_output_file
from openrelik_common.logging import Logger
from openrelik_worker_common.task_utils import create_task_result, get_input_files

from .app import celery

TASK_NAME = "openrelik-worker-ewf-validator.tasks.validate_ewf"

TASK_METADATA = {
    "display_name": "EWF Validator",
    "description": "Validates EWF evidence sets using libewf.",
    "task_config": [],
}

log_root = Logger()
logger = log_root.get_logger(__name__, get_task_logger(__name__))


@signals.task_prerun.connect
def on_task_prerun(sender, task_id, task, args, kwargs, **_):
    log_root.bind(
        task_id=task_id,
        task_name=task.name,
        worker_name=TASK_METADATA["display_name"],
    )


@celery.task(bind=True, name=TASK_NAME, metadata=TASK_METADATA)
def command(
    self,
    pipe_result=None,
    input_files=None,
    output_path=None,
    workflow_id=None,
    task_config=None,
):
    log_root.bind(workflow_id=workflow_id)

    files = get_input_files(pipe_result, input_files or [])

    if not files:
        raise ValueError("No input files supplied")

    with tempfile.TemporaryDirectory() as tmpdir:
        staged = []

        for f in files:
            name = f["display_name"]
            source = f["path"]
            target = Path(tmpdir) / name

            os.symlink(source, target)
            staged.append(target)

        staged = sorted(staged, key=lambda p: p.name)

        e01 = next(
            (p for p in staged if p.suffix.upper() == ".E01"),
            None,
        )

        if not e01:
            raise ValueError("No .E01 segment supplied")

        logger.info(
            f"Validating EWF set starting with {e01.name}"
        )

        info = subprocess.run(
            ["ewfinfo", str(e01)],
            capture_output=True,
            text=True,
        )

        verify = subprocess.run(
            ["ewfverify", "-q", str(e01)],
            capture_output=True,
            text=True,
        )

        version = subprocess.run(
            ["ewfverify", "-V"],
            capture_output=True,
            text=True,
        )

        verification_status = (
            "PASS" if verify.returncode == 0 else "FAIL"
        )

        report = {
            "workflow_id": workflow_id,
            "segments": [p.name for p in staged],
            "tool": "libewf",
            "tool_version": (
                version.stdout.strip()
                or version.stderr.strip()
            ),
            "ewfinfo_return_code": info.returncode,
            "ewfverify_return_code": verify.returncode,
            "verification_status": verification_status,
            "ewfinfo_stdout": info.stdout,
            "ewfinfo_stderr": info.stderr,
            "ewfverify_stdout": verify.stdout,
            "ewfverify_stderr": verify.stderr,
        }

        output_file = create_output_file(
            output_path,
            display_name="ewf-validation-report",
            extension="json",
            data_type="application/json",
        )

        output_path_obj = Path(output_file.path)

        output_path_obj.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path_obj.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        logger.info(
            f"EWF verification completed: {verification_status}"
        )

    return create_task_result(
        output_files=[output_file.to_dict()],
        workflow_id=workflow_id,
        command="ewfinfo + ewfverify",
        meta={
            "verification_status": verification_status,
            "segments": [p.name for p in staged],
        },
    )