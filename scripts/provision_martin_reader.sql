\set ON_ERROR_STOP on
\pset pager off

\if :{?database_name}
\else
  \echo 'missing required psql variable: database_name'
  \quit 3
\endif
\if :{?app_role}
\else
  \echo 'missing required psql variable: app_role'
  \quit 3
\endif
\if :{?martin_role}
\else
  \echo 'missing required psql variable: martin_role'
  \quit 3
\endif

SELECT set_config('martin.database_name', :'database_name', false);
SELECT set_config('martin.app_role', :'app_role', false);
SELECT set_config('martin.reader_role', :'martin_role', false);

DO $provision$
DECLARE
    target_db text := current_setting('martin.database_name');
    app_name text := current_setting('martin.app_role');
    reader_name text := current_setting('martin.reader_role');
    app_oid oid;
    reader_oid oid;
    missing_views text;
    membership record;
    app_function record;
BEGIN
    IF current_database() <> target_db THEN
        RAISE EXCEPTION 'connected to database %, expected %', current_database(), target_db;
    END IF;

    IF app_name = reader_name THEN
        RAISE EXCEPTION 'app_role and martin_role must be different';
    END IF;
    IF lower(reader_name) IN ('postgres', 'public') THEN
        RAISE EXCEPTION 'reserved role name is not allowed for martin_role: %', reader_name;
    END IF;

    SELECT oid INTO app_oid FROM pg_roles WHERE rolname = app_name;
    IF app_oid IS NULL THEN
        RAISE EXCEPTION 'application role does not exist: %', app_name;
    END IF;

    SELECT string_agg(expected.name, ', ' ORDER BY expected.name)
      INTO missing_views
      FROM (
          VALUES
              ('vt_zonas_operativas'),
              ('vt_puntos_conflicto'),
              ('vt_canal_network')
      ) AS expected(name)
     WHERE to_regclass(format('%I.%I', 'public', expected.name)) IS NULL;

    IF missing_views IS NOT NULL THEN
        RAISE EXCEPTION 'run migrations first; missing Martin views: %', missing_views;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = reader_name) THEN
        EXECUTE format('CREATE ROLE %I LOGIN', reader_name);
    END IF;

    SELECT oid INTO reader_oid FROM pg_roles WHERE rolname = reader_name;
    IF EXISTS (SELECT 1 FROM pg_database WHERE datdba = reader_oid)
       OR EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner = reader_oid)
       OR EXISTS (SELECT 1 FROM pg_class WHERE relowner = reader_oid)
       OR EXISTS (SELECT 1 FROM pg_proc WHERE proowner = reader_oid) THEN
        RAISE EXCEPTION
            'Martin role % owns database objects; reassign ownership before provisioning',
            reader_name;
    END IF;

    EXECUTE format(
        'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
        reader_name
    );
    EXECUTE format('ALTER ROLE %I SET default_transaction_read_only = on', reader_name);
    EXECUTE format('ALTER ROLE %I SET search_path = public, pg_catalog', reader_name);

    FOR membership IN
        SELECT parent.rolname AS parent_name
          FROM pg_auth_members AS auth
          JOIN pg_roles AS parent ON parent.oid = auth.roleid
          JOIN pg_roles AS member ON member.oid = auth.member
         WHERE member.rolname = reader_name
    LOOP
        EXECUTE format('REVOKE %I FROM %I', membership.parent_name, reader_name);
    END LOOP;

    FOR membership IN
        SELECT member.rolname AS member_name
          FROM pg_auth_members AS auth
          JOIN pg_roles AS parent ON parent.oid = auth.roleid
          JOIN pg_roles AS member ON member.oid = auth.member
         WHERE parent.rolname = reader_name
    LOOP
        EXECUTE format('REVOKE %I FROM %I', reader_name, membership.member_name);
    END LOOP;

    -- Database and schema access are explicit; PUBLIC is not a fallback path.
    EXECUTE format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', target_db);
    EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', target_db, app_name);
    EXECUTE format('REVOKE ALL PRIVILEGES ON DATABASE %I FROM %I', target_db, reader_name);
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', target_db, reader_name);

    REVOKE CREATE ON SCHEMA public FROM PUBLIC;
    EXECUTE format('GRANT USAGE, CREATE ON SCHEMA public TO %I', app_name);
    EXECUTE format('REVOKE ALL PRIVILEGES ON SCHEMA public FROM %I', reader_name);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', reader_name);

    -- Existing relations: preserve the app owner and remove every reader path.
    REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM PUBLIC;
    REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO %I', app_name);
    EXECUTE format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO %I', app_name);
    EXECUTE format(
        'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I',
        reader_name
    );
    EXECUTE format(
        'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I',
        reader_name
    );
    EXECUTE format(
        'REVOKE ALL PRIVILEGES ON ALL ROUTINES IN SCHEMA public FROM %I',
        reader_name
    );

    -- Extension-owned functions (PostGIS/pgRouting) keep their extension ACLs.
    -- Application-owned and SECURITY DEFINER functions are never reader APIs.
    FOR app_function IN
        SELECT format(
                   '%I.%I(%s)',
                   namespace.nspname,
                   procedure.proname,
                   pg_get_function_identity_arguments(procedure.oid)
               ) AS signature
          FROM pg_proc AS procedure
          JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
         WHERE namespace.nspname = 'public'
           AND (procedure.proowner = app_oid OR procedure.prosecdef)
           AND NOT EXISTS (
               SELECT 1
                 FROM pg_depend AS dependency
                WHERE dependency.classid = 'pg_proc'::regclass
                  AND dependency.objid = procedure.oid
                  AND dependency.deptype = 'e'
           )
    LOOP
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON ROUTINE %s FROM PUBLIC',
            app_function.signature
        );
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON ROUTINE %s FROM %I',
            app_function.signature,
            reader_name
        );
    END LOOP;

    -- Future app-owned objects inherit the same deny-by-default boundary.
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC',
        app_name
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'REVOKE ALL PRIVILEGES ON TABLES FROM %I',
        app_name,
        reader_name
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC',
        app_name
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'REVOKE ALL PRIVILEGES ON SEQUENCES FROM %I',
        app_name,
        reader_name
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'REVOKE EXECUTE ON ROUTINES FROM PUBLIC',
        app_name
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'REVOKE EXECUTE ON ROUTINES FROM %I',
        app_name,
        reader_name
    );

    EXECUTE format(
        'GRANT SELECT ON TABLE '
        'public.vt_zonas_operativas, '
        'public.vt_puntos_conflicto, '
        'public.vt_canal_network TO %I',
        reader_name
    );
END
$provision$;

\echo 'Martin role attributes (all capability flags except LOGIN must be false)'
SELECT rolname,
       rolcanlogin,
       rolsuper,
       rolcreatedb,
       rolcreaterole,
       rolinherit,
       rolreplication,
       rolbypassrls,
       rolconfig
  FROM pg_roles
 WHERE rolname = :'martin_role';

\echo 'Database and schema privileges (CONNECT/USAGE true; CREATE/TEMP false)'
SELECT has_database_privilege(:'martin_role', current_database(), 'CONNECT') AS db_connect,
       has_database_privilege(:'martin_role', current_database(), 'CREATE') AS db_create,
       has_database_privilege(:'martin_role', current_database(), 'TEMPORARY') AS db_temp,
       has_schema_privilege(:'martin_role', 'public', 'USAGE') AS schema_usage,
       has_schema_privilege(:'martin_role', 'public', 'CREATE') AS schema_create;

\echo 'Three allowlisted views (SELECT true; all write columns false)'
SELECT relation.relname,
       has_table_privilege(:'martin_role', relation.oid, 'SELECT') AS can_select,
       has_table_privilege(:'martin_role', relation.oid, 'INSERT') AS can_insert,
       has_table_privilege(:'martin_role', relation.oid, 'UPDATE') AS can_update,
       has_table_privilege(:'martin_role', relation.oid, 'DELETE') AS can_delete,
       has_table_privilege(:'martin_role', relation.oid, 'TRUNCATE') AS can_truncate,
       has_table_privilege(:'martin_role', relation.oid, 'REFERENCES') AS can_reference,
       has_table_privilege(:'martin_role', relation.oid, 'TRIGGER') AS can_trigger
  FROM pg_class AS relation
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
 WHERE namespace.nspname = 'public'
   AND relation.relname IN (
       'vt_zonas_operativas',
       'vt_puntos_conflicto',
       'vt_canal_network'
   )
 ORDER BY relation.relname;

\echo 'The following four checks must each return zero'
SELECT count(*) AS unexpected_relation_privileges
  FROM pg_class AS relation
  JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
 WHERE namespace.nspname = 'public'
   AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
   AND relation.relname NOT IN (
       'vt_zonas_operativas',
       'vt_puntos_conflicto',
       'vt_canal_network'
   )
   AND (
       has_table_privilege(:'martin_role', relation.oid, 'SELECT')
       OR has_table_privilege(:'martin_role', relation.oid, 'INSERT')
       OR has_table_privilege(:'martin_role', relation.oid, 'UPDATE')
       OR has_table_privilege(:'martin_role', relation.oid, 'DELETE')
       OR has_table_privilege(:'martin_role', relation.oid, 'TRUNCATE')
       OR has_table_privilege(:'martin_role', relation.oid, 'REFERENCES')
       OR has_table_privilege(:'martin_role', relation.oid, 'TRIGGER')
   );

SELECT count(*) AS unexpected_sequence_privileges
  FROM pg_class AS sequence
  JOIN pg_namespace AS namespace ON namespace.oid = sequence.relnamespace
 WHERE namespace.nspname = 'public'
   AND sequence.relkind = 'S'
   AND (
       has_sequence_privilege(:'martin_role', sequence.oid, 'USAGE')
       OR has_sequence_privilege(:'martin_role', sequence.oid, 'SELECT')
       OR has_sequence_privilege(:'martin_role', sequence.oid, 'UPDATE')
   );

SELECT count(*) AS unexpected_application_function_privileges
  FROM pg_proc AS procedure
  JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
  JOIN pg_roles AS owner_role ON owner_role.oid = procedure.proowner
 WHERE namespace.nspname = 'public'
   AND (owner_role.rolname = :'app_role' OR procedure.prosecdef)
   AND NOT EXISTS (
       SELECT 1
         FROM pg_depend AS dependency
        WHERE dependency.classid = 'pg_proc'::regclass
          AND dependency.objid = procedure.oid
          AND dependency.deptype = 'e'
   )
   AND has_function_privilege(:'martin_role', procedure.oid, 'EXECUTE');

SELECT count(*) AS unexpected_role_memberships
  FROM pg_auth_members AS auth
  JOIN pg_roles AS parent ON parent.oid = auth.roleid
  JOIN pg_roles AS member ON member.oid = auth.member
 WHERE member.rolname = :'martin_role'
    OR parent.rolname = :'martin_role';
