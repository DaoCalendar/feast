import logging
from concurrent.futures import ThreadPoolExecutor

import grpc

import feast
from feast.core import JobService_pb2_grpc
from feast.core.JobService_pb2 import (
    CancelJobResponse,
    GetHistoricalFeaturesResponse,
    GetJobResponse,
)
from feast.core.JobService_pb2 import Job as JobProto
from feast.core.JobService_pb2 import JobStatus, JobType, ListJobsResponse
from feast.data_source import DataSource
from feast.pyspark.abc import (
    BatchIngestionJob,
    RetrievalJob,
    SparkJob,
    SparkJobStatus,
    StreamIngestionJob,
)
from feast.third_party.grpc.health.v1 import HealthService_pb2_grpc
from feast.third_party.grpc.health.v1.HealthService_pb2 import (
    HealthCheckResponse,
    ServingStatus,
)


class JobServiceServicer(JobService_pb2_grpc.JobServiceServicer):
    def __init__(self):
        self.client = feast.Client()

    def _job_to_proto(self, spark_job: SparkJob) -> JobProto:
        job = JobProto()
        job.id = spark_job.get_id()
        status = spark_job.get_status()
        if status == SparkJobStatus.COMPLETED:
            job.status = JobStatus.JOB_STATUS_DONE
        elif status == SparkJobStatus.IN_PROGRESS:
            job.status = JobStatus.JOB_STATUS_RUNNING
        elif status == SparkJobStatus.FAILED:
            job.status = JobStatus.JOB_STATUS_ERROR
        elif status == SparkJobStatus.STARTING:
            job.status = JobStatus.JOB_STATUS_PENDING
        else:
            raise ValueError(f"Invalid job status {status}")

        if isinstance(spark_job, RetrievalJob):
            job.type = JobType.RETRIEVAL_JOB
            job.retrieval.output_location = spark_job.get_output_file_uri(block=False)
        elif isinstance(spark_job, BatchIngestionJob):
            job.type = JobType.BATCH_INGESTION_JOB
        elif isinstance(spark_job, StreamIngestionJob):
            job.type = JobType.STREAM_INGESTION_JOB
        else:
            raise ValueError(f"Invalid job type {job}")

        return job

    def StartOfflineToOnlineIngestionJob(self, request, context):
        """Start job to ingest data from offline store into online store"""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def GetHistoricalFeatures(self, request, context):
        """Produce a training dataset, return a job id that will provide a file reference"""
        job = self.client.get_historical_features(
            request.feature_refs,
            entity_source=DataSource.from_proto(request.entity_source),
            project=request.project,
            output_location=request.output_location,
        )

        output_file_uri = job.get_output_file_uri(block=False)

        return GetHistoricalFeaturesResponse(
            id=job.get_id(), output_file_uri=output_file_uri
        )

    def StartStreamToOnlineIngestionJob(self, request, context):
        """Start job to ingest data from stream into online store"""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def ListJobs(self, request, context):
        """List all types of jobs"""
        jobs = self.client.list_jobs(include_terminated=request.include_terminated)
        return ListJobsResponse(jobs=[self._job_to_proto(job) for job in jobs])

    def CancelJob(self, request, context):
        """Stop a single job"""
        job = self.client.get_job_by_id(request.job_id)
        job.cancel()
        return CancelJobResponse()

    def GetJob(self, request, context):
        """Get details of a single job"""
        job = self.client.get_job_by_id(request.job_id)
        return GetJobResponse(job=self._job_to_proto(job))


class HealthServicer(HealthService_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        return HealthCheckResponse(status=ServingStatus.SERVING)


class LoggingInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        logging.info(handler_call_details)
        return continuation(handler_call_details)


def start_job_service():
    """
    Start Feast Job Service
    """

    log_fmt = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_fmt)

    server = grpc.server(ThreadPoolExecutor(), interceptors=(LoggingInterceptor(),))
    JobService_pb2_grpc.add_JobServiceServicer_to_server(JobServiceServicer(), server)
    HealthService_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
    server.add_insecure_port("[::]:6568")
    server.start()
    print("Feast job server listening on port :6568")
    server.wait_for_termination()
