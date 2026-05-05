"""feds aurora database."""

import argparse
import os
from pathlib import Path
from typing import Literal

import boto3
import geopandas as gpd
import psycopg2
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine


# Needs to be set as environment variable in Hyp3
DB_HOST = os.environ.get('DB_HOST', None)

# AWS Defaults
DB_PORT = os.environ.get('DB_PORT', 5432)
DB_NAME = os.environ.get('DB_NAME', 'postgres')
DB_USER = os.environ.get('DB_USER', 'postgres')
AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')


# For use in HyP3, access info needs to be set as environment variable in CI/CD
def get_auth_token(aws_profile: str | None = None) -> str:
    """Retrieves an AWS RDS token for use as a password for DB connections."""
    session = boto3.Session(profile_name=aws_profile)
    client = session.client('rds')
    token = client.generate_db_auth_token(
        DBHostname=DB_HOST,
        Port=DB_PORT,
        DBUsername=DB_USER,
        Region=AWS_REGION,
    )
    return token


def get_db_connection() -> psycopg2.extensions.connection:
    """Creates a PostgreSQL connection for queries and extension management."""
    token = get_auth_token()
    connection = psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=token, port=DB_PORT, sslmode='require'
    )
    return connection


def get_db_engine() -> Engine:
    """Creates a SQLAlchemy Engine for Geopanda's `to_postgis`."""
    token = get_auth_token()
    url_object = URL.create(
        'postgresql',
        username=DB_USER,
        password=token,
        host=DB_HOST,
        database=DB_NAME,
    )
    engine = create_engine(url_object, plugins=['geoalchemy2'])
    return engine


def enable_postgis_extension() -> None:
    """Enables the PostGIS extension on the PostgreSQL database."""
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS postgis;')
    connection.commit()


def fetch_one_from_db(query: str) -> tuple | None:
    """Queries the database and returns the result of `fetchone`.

    Args:
        query: The query to be run.

    Returns:
        The result of fetchone() after the query.
    """
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute(query)
        result = cursor.fetchone()
    return result


def check_postgis_extension() -> tuple | None:
    """Verifies that the PostGIS extension is enabled on the PostgreSQL database."""
    return fetch_one_from_db('SELECT postgis_full_version();')


def check_users() -> tuple | None:
    """Verifies that the PostGIS extension is enabled on the PostgreSQL database."""
    return fetch_one_from_db('SELECT * FROM pg_catalog.pg_user;')


def add_user_to_db(
    username: str,
    password: str,
) -> None:
    """Add a read-only user to the database.

    Args:
        username: The username of the new user.
        password: The password of the new user.
    """
    connection = get_db_connection()
    with connection.cursor() as cursor:
        cursor.execute(f"""
            CREATE USER {username} IF NOT EXISTS WITH PASSWORD \'{password}\';
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO {username};
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT ON TABLES TO {username};
        """)
    connection.commit()


def upload_parquet_to_db(
    geoparquet_path: str | Path,
    table_name: str = 'feds_table',
    schema: str = 'public',
    index_label: str = 'fireID',
    if_exists: Literal['fail', 'replace', 'append'] = 'replace',
    geometry_columns: list[str] = ['hull', 'fline', 'nfp'],
) -> None:
    """Read a GeoParquet file and write its columns to Amazon RDS PostgreSQL/PostGIS.

    Args:
        geoparquet_path: Path to the input GeoParquet file.
        rds_uri: SQLAlchemy connection URI, for example: postgresql+psycopg2://user:password@host:5432/dbname
        table_name: Destination table name.
        schema: PostgreSQL schema name.
        index_label: The name of the column to use as the index.
        if_exists: One of: "fail", "replace", or "append".
        geometry_columns: List of columns with geometry types.
    """
    gdf = gpd.read_parquet(geoparquet_path)

    upload_gdf_to_db(
        gdf=gdf,
        table_name=table_name,
        schema=schema,
        index_label=index_label,
        if_exists=if_exists,
        geometry_columns=geometry_columns,
    )


def upload_gdf_to_db(
    gdf: gpd.geodataframe.GeoDataFrame,
    table_name: str = 'feds_table',
    schema: str = 'public',
    index_label: str = 'fireID',
    if_exists: Literal['fail', 'replace', 'append'] = 'replace',
    geometry_columns: list[str] = ['hull', 'fline', 'nfp'],
) -> None:
    """Upload a GeoDataFrame to Amazon RDS PostgreSQL/PostGIS.

    Args:
        gdf: The GeoDataFrame to upload.
        rds_uri: SQLAlchemy connection URI, for example: postgresql+psycopg2://user:password@host:5432/dbname
        table_name: Destination table name.
        schema: PostgreSQL schema name.
        index_label: The name of the column to use as the index.
        if_exists: One of: "fail", "replace", or "append".
        geometry_columns: List of columns with geometry types.
    """
    for geom_col in geometry_columns:
        gdf.set_geometry(geom_col)

    engine = get_db_engine()

    gdf.to_postgis(
        name=table_name,
        con=engine,
        schema=schema,
        index_label=index_label,
        if_exists=if_exists,
    )


def main() -> None:
    """CLI Entrypoint for enabling postgis, and adding read-only users."""
    parser = argparse.ArgumentParser(description='CLI entrypoint for adding read-only users and enabling PostGIS.')
    parser.add_argument('--username', type=str, default=None, help='The username for the new user.')
    parser.add_argument('--password', type=str, default=None, help='The password for the new user.')
    parser.add_argument('--enable-postgis', type=bool, default=True, help='Whether to enable PostGIS or not.')
    args = parser.parse_args()

    if args.enable_postgis:
        enable_postgis_extension()
        result = check_postgis_extension()
        assert result is not None

    if args.username:
        if args.password is None:
            raise ValueError('A password is required when creating a new user.')

        try:
            add_user_to_db(args.username, args.password)
        except psycopg2.errors.DuplicateObject:
            print(f'User `{args.username}` already exists.')


if __name__ == '__main__':
    main()
