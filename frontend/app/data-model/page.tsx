import Link from "next/link";
import { ApiDownNotice, Pill } from "@/components/ui";
import {
  ApiUnavailable,
  dataModel,
  type DataModelFamily,
  type DataModelTable,
  type DataModelView,
} from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * One table, exactly as the ORM declares it.
 *
 * Collapsed by default: thirty-one tables expanded at once is a schema dump, not
 * documentation. The head line carries what a reader scanning for the right
 * table needs — what it holds, how many columns, and whether it has rows here.
 */
function TableCard({ table }: { table: DataModelTable }) {
  const foreignKeys = new Map(table.foreign_keys.map(([column, target]) => [column, target]));
  return (
    <details className="dm-table" id={table.name}>
      <summary>
        <span className="mono dm-table-name">{table.name}</span>
        <span className="muted dm-table-meta">
          {table.columns.length} columns
          {table.row_count != null
            ? ` · ${table.row_count.toLocaleString()} row${table.row_count === 1 ? "" : "s"} here`
            : ""}
        </span>
        {table.populated_by_capability ? (
          <span className="dm-capability mono" title="Connector capability that populates this table">
            {table.populated_by_capability}
          </span>
        ) : null}
      </summary>

      {table.purpose ? (
        <p className="muted" style={{ maxWidth: "84ch", marginTop: "0.6rem" }}>
          {table.purpose}
        </p>
      ) : null}

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Column</th>
              <th>Type</th>
              <th>Postgres</th>
              <th>Null</th>
              <th>Key</th>
            </tr>
          </thead>
          <tbody>
            {table.columns.map((column) => {
              const target = foreignKeys.get(column.name);
              return (
                <tr key={column.name}>
                  <td className="mono">{column.name}</td>
                  <td className="mono muted" style={{ fontSize: "0.76rem" }}>{column.type}</td>
                  <td className="mono muted" style={{ fontSize: "0.76rem" }}>{column.postgres_type}</td>
                  <td className="muted">{column.nullable ? "yes" : "no"}</td>
                  <td className="muted" style={{ fontSize: "0.76rem" }}>
                    {column.primary_key ? <span className="dm-key">PK</span> : null}
                    {target ? (
                      <a className="dm-key dm-key-fk" href={`#${target.split(".")[0]}`}>
                        FK → {target}
                      </a>
                    ) : null}
                    {column.unique && !column.primary_key ? <span className="dm-key">unique</span> : null}
                    {column.indexed && !column.primary_key ? <span className="dm-key">index</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {table.unique_constraints.length ? (
        <p className="muted mono" style={{ fontSize: "0.78rem" }}>
          {table.unique_constraints
            .map((constraint) => `${constraint.name} (${constraint.columns.join(", ")})`)
            .join(" · ")}
        </p>
      ) : null}

      <details className="dm-ddl">
        <summary className="muted">Postgres DDL</summary>
        <pre className="mono">{table.postgres_ddl}</pre>
      </details>
    </details>
  );
}

function Family({ family }: { family: DataModelFamily }) {
  const rows = family.tables.reduce((total, table) => total + (table.row_count ?? 0), 0);
  return (
    <section className="card" id={family.key}>
      <div className="api-connector-head">
        <div>
          <h2 style={{ margin: 0 }}>{family.name}</h2>
          <div className="muted mono" style={{ fontSize: "0.78rem" }}>
            {family.tables.length} tables · {rows.toLocaleString()} rows on this instance
          </div>
        </div>
        <Pill label={family.lifecycle} color="var(--ocean-600)" />
      </div>
      <p className="muted" style={{ maxWidth: "84ch" }}>{family.summary}</p>
      {family.tables.map((table) => (
        <TableCard key={table.name} table={table} />
      ))}
    </section>
  );
}

export default async function DataModelPage() {
  let model: DataModelView;
  try {
    model = await dataModel();
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  const { deployment, totals } = model;

  return (
    <>
      <div className="eyebrow">Data model</div>
      <h1>The database underneath</h1>
      <p className="lede">
        Every table, column, key and index below is read from the ORM as this page renders. Nothing
        here is transcribed, so the schema and its documentation cannot disagree — a migration that
        adds a column adds it to this page.
      </p>

      <div className="grid cols-4" style={{ margin: "1.4rem 0" }}>
        <div className="metric">
          <div className="eyebrow">Tables</div>
          <strong>{totals.tables}</strong>
          <small>Across {model.families.length} families</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Columns</div>
          <strong>{totals.columns}</strong>
          <small>{totals.indexes} indexes</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Foreign keys</div>
          <strong>{totals.foreign_keys}</strong>
          <small>Tenant-keyed tables cascade on delete</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Rows here</div>
          <strong>{totals.rows?.toLocaleString() ?? "—"}</strong>
          <small>This instance, right now</small>
        </div>
      </div>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Where it runs</h2>
        <p className="muted" style={{ maxWidth: "84ch" }}>
          One relational database, no extensions, no cloud-specific objects. Moving between
          hyperscalers changes the connection string and nothing else — which is the point of
          keeping the rubric, the evidence and the canonical model in ordinary tables.
        </p>

        <div
          className="banner"
          style={
            deployment.is_production_target
              ? undefined
              : { borderColor: "var(--severity-medium)", opacity: 0.95 }
          }
        >
          <h3>
            This instance is running on{" "}
            <span className="mono">{deployment.current_dialect || "an unknown dialect"}</span>
          </h3>
          <p style={{ margin: "0 0 0.4rem" }}>
            {deployment.is_production_target
              ? "A supported production target."
              : "Fine for development and CI. Set EAIRN_DATABASE_URL to Postgres before a hosted deployment takes its first harvest."}
          </p>
          <div className="muted mono">{deployment.current_url || "no database URL configured"}</div>
        </div>

        <div className="grid cols-3">
          {deployment.targets.map((target) => (
            <div key={target.platform} className="api-panel">
              <div className="eyebrow">{target.platform}</div>
              <strong style={{ fontSize: "0.92rem" }}>{target.service}</strong>
              <pre className="mono dm-url">{target.url}</pre>
              <p className="muted" style={{ fontSize: "0.83rem" }}>{target.detail}</p>
            </div>
          ))}
        </div>

        {deployment.notes.map((note) => (
          <div key={note.heading}>
            <h3>{note.heading}</h3>
            <p className="muted" style={{ maxWidth: "84ch" }}>{note.body}</p>
          </div>
        ))}
      </section>

      {model.families.map((family) => (
        <Family key={family.key} family={family} />
      ))}

      <section className="card" id="relationships">
        <h2 style={{ marginTop: 0 }}>How the tables join</h2>
        <p className="muted" style={{ maxWidth: "84ch" }}>
          Every foreign key in the schema. The cascade column is the retention story: deleting an
          organisation removes its estate and its snapshots in one statement, because each of those
          paths cascades back to <span className="mono">tenants</span>.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>From</th>
                <th>To</th>
                <th>On delete</th>
              </tr>
            </thead>
            <tbody>
              {model.relationships.map((edge) => (
                <tr key={`${edge.from_table}.${edge.from_column}`}>
                  <td className="mono">
                    <a href={`#${edge.from_table}`}>{edge.from_table}</a>.{edge.from_column}
                  </td>
                  <td className="mono">
                    <a href={`#${edge.to_table}`}>{edge.to_table}</a>.{edge.to_column}
                  </td>
                  <td className="muted mono" style={{ fontSize: "0.76rem" }}>
                    {edge.on_delete || "restrict"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="muted" style={{ maxWidth: "84ch" }}>
        The <span className="mono">capability</span> badge on a canonical table names the connector
        capability that fills it. To trace one back to the platform call that produced it, see the{" "}
        <Link href="/api-docs#capabilities">capability matrix</Link>.
      </p>
    </>
  );
}
