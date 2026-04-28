"""feds aurora database."""

import os
from pathlib import Path

import boto3
import geopandas as gpd
import psycopg2
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine


proxy_host_name = os.environ['PROXY_HOST_NAME']
port = int(os.environ['PORT'])
db_name = os.environ['DB_NAME']
db_user_name = os.environ['DB_USER_NAME']
aws_region = os.environ['AWS_REGION']


# TODO: Need an IAM user/role that is created on deployment
def get_auth_token(aws_profile: str | None = None) -> str:
    """Retrieves an AWS RDS token for use as a password for DB connections."""
    session = boto3.Session(profile_name=aws_profile)
    client = session.client('rds')
    token = client.generate_db_auth_token(DBHostname=proxy_host_name,Port=port,DBUsername=db_user_name,Region=aws_region)
    return token


def get_db_connection() -> psycopg2.extensions.connection:
    """Creates a PostgreSQL connection for queries and extension management."""
    token = get_auth_token()
    connection = psycopg2.connect(
        host=proxy_host_name,
        dbname=db_name,
        user=db_user_name,
        password=token,
        port=port,
        sslmode='require'
    )
    return connection


def get_db_engine() -> Engine:
    """Creates a SQLAlchemy Engine for Geopanda's `to_postgis`."""
    token = get_auth_token()
    url_object = URL.create(
        "postgresql",
        username=db_user_name,
        password=token,
        host=proxy_host_name,
        database=db_name,
    )
    engine = create_engine(url_object, plugins=["geoalchemy2"])
    return engine


def enable_postgis_extension() -> None:
    """Enables the PostGIS extension on the PostgreSQL database."""
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS postgis;')
    connection.commit()


def check_postgis_extension() -> str:
    """Verifies that the PostGIS extension is enabled on the PostgreSQL database."""
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('SELECT postgis_full_version();')
        result = cursor.fetchone()[0]
    return result


def create_feds_table(
    geoparquet_path: str | Path,
    table_name: str,
    schema: str = "public",
    if_exists: str = "append",
    geometry_columns: list[str] = ['hull', 'fline', 'nfp']
) -> None:
    """Read a GeoParquet file and write its columns to Amazon RDS PostgreSQL/PostGIS.

    Args:
    ----------
        geoparquet_path: Path to the input GeoParquet file.
        rds_uri: SQLAlchemy connection URI, for example: postgresql+psycopg2://user:password@host:5432/dbname
        table_name: Destination table name.
        schema: PostgreSQL schema name.
        if_exists: One of: "fail", "replace", or "append".
        geometry_columns: List of columns with geometry types.
    """
    gdf = gpd.read_parquet(geoparquet_path)

    for geom_col in geometry_columns:
        gdf.set_geometry(geom_col)

    engine = get_db_engine()

    gdf.to_postgis(
        name=table_name,
        con=engine,
        schema=schema,
        if_exists=if_exists,
        index=False,
    )


def query_feds_table(query: str) -> None:
    """Query the database."""
    # TODO: 
    return None
