"""Airflow DAG: batch data preparation. Real-time recommendations are served by FastAPI, never by Airflow."""
from datetime import datetime, timedelta

from airflow.decorators import dag, task

DEFAULT_ARGS = {"retries": 2, "retry_delay": timedelta(minutes=5), "owner": "data-platform"}


@dag(dag_id="team_selection_etl", schedule="0 2 * * *", start_date=datetime(2026, 1, 1), catchup=False,
     default_args=DEFAULT_ARGS, tags=["team-selection"], max_active_runs=1)
def team_selection_etl():
    @task
    def extract_validate_normalise() -> dict:
        from teamselect import etl
        return etl.extract_and_validate()          # writes staging + rejected records

    @task
    def load(stats: dict) -> dict:
        from teamselect import etl
        return etl.load()                           # transactional rebuild of the serving DB

    @task
    def data_quality_gate(_: dict) -> dict:
        from teamselect import etl
        return etl.quality_check()                  # raises => DAG fails => alert, previous data keeps serving

    data_quality_gate(load(extract_validate_normalise()))


team_selection_etl()
