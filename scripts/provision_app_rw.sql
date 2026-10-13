\set ON_ERROR_STOP on
\pset pager off

\if :{?database_name}
\else
  \echo 'missing required psql variable: database_name'
  \quit 3
\endif
\if :{?migrator_role}
\else
  \echo 'missing required psql variable: migrator_role'
  \quit 3
\endif
\if :{?app_role}
\else
  \echo 'missing required psql variable: app_role'
  \quit 3
\endif

SELECT set_config('appdb.database_name', :'database_name', false);
SELECT set_config('appdb.migrator_role', :'migrator_role', false);
SELECT set_config('appdb.app_role', :'app_role', false);

DO $provision$
DECLARE
    target_db text := current_setting('appdb.database_name');
    migrator_name text := current_setting('appdb.migrator_role');
    app_name text := current_setting('appdb.app_role');
    rel record;
    idx record;
BEGIN
    IF current_database() <> target_db THEN
        RAISE EXCEPTION 'connected to database %, expected %', current_database(), target_db;
    END IF;

    IF migrator_name = app_name THEN
        RAISE EXCEPTION 'migrator_role and app_role must be different';
    END IF;
    IF lower(app_name) IN ('postgres', 'public') THEN
        RAISE EXCEPTION 'reserved role name is not allowed for app_role: %', app_name;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = migrator_name) THEN
        RAISE EXCEPTION 'migrator role does not exist: %', migrator_name;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_name) THEN
        EXECUTE format('CREATE ROLE %I LOGIN', app_name);
    END IF;

    EXECUTE format(
        'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
        app_name
    );
    EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', app_name, '15s');
    EXECUTE format(
        'ALTER ROLE %I SET idle_in_transaction_session_timeout = %L',
        app_name,
        '60s'
    );
    EXECUTE format('ALTER ROLE %I SET search_path = public, pg_catalog', app_name);

    EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', target_db, app_name);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', app_name);
    EXECUTE format('REVOKE CREATE ON SCHEMA public FROM %I', app_name);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', app_name);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', app_name);
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
        migrator_name,
        app_name
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'GRANT USAGE, SELECT ON SEQUENCES TO %I',
        migrator_name,
        app_name
    );

    -- PostgreSQL has no GRANT REFRESH. The API refreshes these views, so the
    -- app role must own them (and their indexes). Everything else stays on
    -- the migrator. Installing extensions stays on the migrator.
    FOR rel IN
        SELECT c.oid, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'm'
          AND c.relname = ANY (ARRAY[
              'mv_dashboard_geo_stats',
              'mv_hci_por_zona',
              'mv_alertas_resumen',
              'mv_suelos_por_zona',
              'mv_canales_por_zona',
              'mv_caminos_por_zona',
              'vt_parcelas_catastro'
          ])
    LOOP
        EXECUTE format(
            'ALTER MATERIALIZED VIEW public.%I OWNER TO %I',
            rel.relname,
            app_name
        );
        FOR idx IN
            SELECT ic.relname
            FROM pg_index i
            JOIN pg_class ic ON ic.oid = i.indexrelid
            WHERE i.indrelid = rel.oid
        LOOP
            EXECUTE format('ALTER INDEX public.%I OWNER TO %I', idx.relname, app_name);
        END LOOP;
    END LOOP;
END
$provision$;

\echo 'App role flags (rolsuper must be false)'
SELECT rolname,
       rolcanlogin,
       rolsuper,
       rolcreatedb,
       rolcreaterole,
       rolconfig
  FROM pg_roles
 WHERE rolname = :'app_role';
