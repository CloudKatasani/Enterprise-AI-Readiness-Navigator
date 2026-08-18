import { ApiDownNotice, Pill } from "@/components/ui";
import {
  ApiUnavailable,
  integrationGuide,
  type IntegrationCall,
  type IntegrationConnector,
  type IntegrationCoverage,
  type IntegrationView,
} from "@/lib/api";

export const dynamic = "force-dynamic";

/** Paragraphs from a YAML block scalar. */
function Prose({ text, className }: { text: string; className?: string }) {
  if (!text) return null;
  return (
    <>
      {text
        .trim()
        .split(/\n\s*\n/)
        .map((paragraph, index) => (
          <p key={index} className={className} style={{ maxWidth: "84ch" }}>
            {paragraph.replace(/\s*\n\s*/g, " ")}
          </p>
        ))}
    </>
  );
}

/**
 * One catalogued statement or endpoint, exactly as the connector will issue it.
 *
 * The read-only badge is not decoration: the backend re-runs the same guard the
 * executor uses while rendering this page, so a statement that could mutate a
 * customer platform could not appear here unflagged.
 */
function Call({ call }: { call: IntegrationCall }) {
  return (
    <div className="api-call">
      <div className="api-call-head">
        <span className="mono api-call-name">{call.name}</span>
        {call.kind === "http" ? (
          <span className={`api-method${call.method === "POST" ? " api-method-post" : ""}`}>
            {call.method}
          </span>
        ) : (
          <span className="api-method api-method-sql">SQL</span>
        )}
        {call.read_only_verified ? (
          <span className="api-verified" title="Re-validated by the read-only guard as this page rendered">
            read-only verified
          </span>
        ) : (
          <span className="api-unverified">failed the read-only guard</span>
        )}
        {call.reviewed_read_only_post ? (
          <span className="muted" style={{ fontSize: "0.72rem" }}>
            search endpoint, reviewed as non-mutating
          </span>
        ) : null}
      </div>
      <pre className="mono api-statement">{call.statement}</pre>
    </div>
  );
}

/** What connecting this platform buys, in checks rather than in adjectives. */
function Coverage({ coverage }: { coverage: IntegrationCoverage }) {
  const total = coverage.unlocked_count + coverage.blocked_count;
  return (
    <>
      <div className="coverage-bar" title={`${coverage.unlocked_count} of ${total} checks`}>
        <div
          className="coverage-fill"
          style={{ width: `${total ? (coverage.unlocked_count / total) * 100 : 0}%` }}
        />
      </div>
      <p className="muted" style={{ fontSize: "0.82rem", margin: "0.4rem 0 0.7rem" }}>
        Connected on its own, this platform supplies evidence for{" "}
        <strong>{coverage.unlocked_count}</strong> of {total} registered checks. The other{" "}
        {coverage.blocked_count} report as <em>not measured</em> until another source covers them —
        they are never scored as zero.
      </p>
      <div className="coverage-pillars">
        {coverage.by_pillar.map((pillar) => (
          <div key={pillar.pillar_key} className="coverage-pillar">
            <div className="eyebrow">{pillar.pillar_name}</div>
            <div className="mono" style={{ fontSize: "0.76rem" }}>
              {pillar.checks.map((check) => check.check_id).join(" · ")}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function ConnectorCard({ connector }: { connector: IntegrationConnector }) {
  return (
    <section className="card api-connector" id={connector.key}>
      <div className="api-connector-head">
        <div>
          <h3 style={{ margin: 0 }}>{connector.display_name}</h3>
          <div className="muted mono" style={{ fontSize: "0.78rem" }}>
            key {connector.key} · platform {connector.platform}
          </div>
        </div>
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
          <Pill
            label={connector.live_harvest_available ? "live driver" : `bundle-backed · ${connector.roadmap_phase}`}
            color={connector.live_harvest_available ? "var(--grade-ready)" : "var(--severity-low)"}
          />
          <Pill label="read-only" color="var(--ocean-600)" />
        </div>
      </div>

      <Prose text={connector.summary} />

      {!connector.live_harvest_available ? (
        <p className="muted" style={{ fontSize: "0.84rem", maxWidth: "84ch" }}>
          The live driver{connector.live_driver ? ` (${connector.live_driver})` : ""} lands in{" "}
          {connector.roadmap_phase}. Until then this platform is assessed from a canonical metadata
          bundle, which produces the same evidence and the same score — see below.
        </p>
      ) : null}

      {connector.preconditions.length ? (
        <>
          <h4>Before it will work</h4>
          <ul className="muted api-list">
            {connector.preconditions.map((precondition) => (
              <li key={precondition}>{precondition}</li>
            ))}
          </ul>
        </>
      ) : null}

      <h4>Authentication</h4>
      <ul className="api-list">
        {connector.auth.map((mode) => (
          <li key={mode.mode}>
            <strong>{mode.mode}</strong>
            {mode.recommended ? <span className="api-recommended">recommended</span> : null}
            <div className="muted" style={{ fontSize: "0.83rem" }}>{mode.detail}</div>
          </li>
        ))}
      </ul>

      {connector.config_fields.length ? (
        <>
          <h4>Connection configuration</h4>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Required</th>
                  <th>Example</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {connector.config_fields.map((field) => (
                  <tr key={field.key}>
                    <td className="mono">
                      {field.key}
                      {field.secret ? <span className="api-secret">secret</span> : null}
                    </td>
                    <td className="muted">{field.required ? "yes" : "optional"}</td>
                    <td className="mono muted" style={{ fontSize: "0.76rem" }}>
                      {field.example}
                    </td>
                    <td className="muted">{field.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ fontSize: "0.8rem" }}>
            Values marked <em>secret</em> are read from the platform&apos;s secret store at run
            time. They are never persisted on the connection row and never appear in the provenance
            recorded against a harvest, so the examples above are placeholders or mount paths — a
            test asserts that no real credential can reach this table.
          </p>
        </>
      ) : null}

      <h4>Least-privilege grant</h4>
      <p className="muted" style={{ margin: "0 0 0.5rem" }}>
        {connector.permission_manifest.principal}
      </p>
      <ul className="api-list">
        {connector.permission_manifest.grants.map((grant) => (
          <li key={grant.grant}>
            <span className="mono" style={{ fontSize: "0.8rem" }}>{grant.grant}</span>
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              {grant.scope} — {grant.purpose}
            </div>
          </li>
        ))}
      </ul>
      {connector.permission_manifest.notes ? (
        <p className="muted" style={{ fontSize: "0.83rem" }}>{connector.permission_manifest.notes}</p>
      ) : null}

      {connector.egress.length ? (
        <>
          <h4>Network egress</h4>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Host</th>
                  <th>Port</th>
                  <th>Purpose</th>
                </tr>
              </thead>
              <tbody>
                {connector.egress.map((egress) => (
                  <tr key={egress.host}>
                    <td className="mono">{egress.host}</td>
                    <td className="num mono">{egress.port}</td>
                    <td className="muted">{egress.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {connector.calls.length ? (
        <>
          <h4>Everything it calls</h4>
          <p className="muted" style={{ fontSize: "0.83rem", maxWidth: "84ch" }}>
            This is the complete catalog — the connector cannot issue a statement or reach an
            endpoint that is not on this list.
          </p>
          {connector.calls.map((call) => (
            <Call key={`${call.kind}-${call.name}`} call={call} />
          ))}
        </>
      ) : null}

      <h4>What it unlocks</h4>
      <Coverage coverage={connector.coverage} />

      <div className="api-facts">
        {connector.freshness ? (
          <div>
            <div className="eyebrow">Freshness</div>
            <p className="muted">{connector.freshness}</p>
          </div>
        ) : null}
        {connector.pagination ? (
          <div>
            <div className="eyebrow">Paging</div>
            <p className="muted">{connector.pagination}</p>
          </div>
        ) : null}
        {connector.limits ? (
          <div>
            <div className="eyebrow">Limits</div>
            <p className="muted">{connector.limits}</p>
          </div>
        ) : null}
      </div>

      {connector.vendor_docs.length ? (
        <div className="refs">
          <h4>Vendor documentation</h4>
          <ol>
            {connector.vendor_docs.map((doc) => (
              <li key={doc.url}>
                <a href={doc.url} target="_blank" rel="noreferrer noopener">
                  {doc.title}
                </a>
              </li>
            ))}
          </ol>
          <p className="muted" style={{ fontSize: "0.78rem", marginBottom: 0 }}>
            Rate limits and retention windows move on the vendor&apos;s schedule. Treat the numbers
            above as sizing guidance and confirm them here before a production rollout.
          </p>
        </div>
      ) : null}
    </section>
  );
}

export default async function ApiDocsPage() {
  let guide: IntegrationView;
  try {
    guide = await integrationGuide();
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  const { hosting, totals } = guide;

  return (
    <>
      <div className="eyebrow">API documentation</div>
      <h1>Wiring EAIRN to real platforms</h1>
      <p className="lede">{guide.intro.headline}</p>
      <Prose text={guide.intro.body} className="muted" />

      <div className="grid cols-4" style={{ margin: "1.4rem 0" }}>
        <div className="metric">
          <div className="eyebrow">Connectors</div>
          <strong>{totals.connectors}</strong>
          <small>
            {totals.live_drivers} live driver{totals.live_drivers === 1 ? "" : "s"},{" "}
            {totals.bundle_backed} bundle-backed
          </small>
        </div>
        <div className="metric">
          <div className="eyebrow">Catalogued calls</div>
          <strong>{totals.documented_calls}</strong>
          <small>Every statement and endpoint, published verbatim</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Checks they feed</div>
          <strong>{totals.registered_checks}</strong>
          <small>A check with no evidence is not measured, never zero</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Read-only violations</div>
          <strong style={{ color: totals.read_only_violations ? "var(--severity-critical)" : undefined }}>
            {totals.read_only_violations}
          </strong>
          <small>Re-checked as this page rendered, and asserted in CI</small>
        </div>
      </div>

      {/* Deployment first: the connector detail below is unusable until the
          runtime it lives in has a database, a secret store and egress. */}
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Hosting the application</h2>
        <Prose text={hosting.summary} className="muted" />

        <h3>What runs</h3>
        <ul className="api-list">
          {hosting.runtime.map((piece) => (
            <li key={piece.name}>
              <strong>{piece.name}</strong>
              <div className="muted" style={{ fontSize: "0.84rem" }}>{piece.detail}</div>
            </li>
          ))}
        </ul>

        <h3>Secrets</h3>
        <div className="grid cols-3">
          {hosting.secrets.map((secret) => (
            <div key={secret.platform} className="api-panel">
              <div className="eyebrow">{secret.platform}</div>
              <strong style={{ fontSize: "0.92rem" }}>{secret.service}</strong>
              <p className="muted" style={{ fontSize: "0.83rem" }}>{secret.detail}</p>
            </div>
          ))}
        </div>

        <h3>Network</h3>
        <Prose text={hosting.network.summary} className="muted" />
        <ul className="muted api-list">
          {hosting.network.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>

        <h3>Backend environment</h3>
        <p className="muted" style={{ maxWidth: "84ch" }}>{hosting.environment.intro}</p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Variable</th>
                <th>Example</th>
                <th>This instance</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {hosting.environment.variables.map((variable) => (
                <tr key={variable.name}>
                  <td className="mono">{variable.name}</td>
                  <td className="mono muted" style={{ fontSize: "0.76rem" }}>{variable.example}</td>
                  <td className="mono" style={{ fontSize: "0.76rem" }}>{variable.current || "—"}</td>
                  <td className="muted">{variable.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3>Bringing a platform online</h3>
        <ol className="api-steps">
          {hosting.sequence.map((step) => (
            <li key={step.step}>
              <strong>{step.step}</strong>
              <div className="muted" style={{ fontSize: "0.85rem" }}>{step.detail}</div>
            </li>
          ))}
        </ol>
      </section>

      <h2 id="connectors">Connectors</h2>
      <p className="muted" style={{ maxWidth: "84ch" }}>
        Live drivers first, then by roadmap phase. Each card is everything needed to configure that
        platform: the credential to mint, the keys to set, the hosts to allow, the exact calls
        EAIRN will make, and the checks that stop reporting as not measured once it is connected.
      </p>
      {guide.connectors.map((connector) => (
        <ConnectorCard key={connector.key} connector={connector} />
      ))}

      <section className="card" id="capabilities">
        <h2 style={{ marginTop: 0 }}>Capability matrix</h2>
        <p className="muted" style={{ maxWidth: "84ch" }}>
          Read this column-first when scoping a rollout. A capability is a family of metadata EAIRN
          can observe; the checks in the right-hand column stay unmeasured until at least one
          connector supplying that capability is connected.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Capability</th>
                <th>Supplied by</th>
                <th className="num">Checks</th>
                <th>Which checks</th>
              </tr>
            </thead>
            <tbody>
              {guide.capability_matrix.map((row) => (
                <tr key={row.capability}>
                  <td className="mono">{row.capability}</td>
                  <td className="muted" style={{ fontSize: "0.78rem" }}>
                    {row.connectors.join(", ") || "no connector"}
                  </td>
                  <td className="num">{row.check_count}</td>
                  <td className="mono muted" style={{ fontSize: "0.76rem" }}>
                    {row.checks.map((check) => check.check_id).join(" · ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" id="canonical-bundle">
        <h2 style={{ marginTop: 0 }}>The canonical bundle path</h2>
        <Prose text={guide.canonical_bundle.summary} className="muted" />
        <Prose text={guide.canonical_bundle.why} className="muted" />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Entity</th>
                <th>What it carries</th>
              </tr>
            </thead>
            <tbody>
              {guide.canonical_bundle.fields.map((field) => (
                <tr key={field.entity}>
                  <td className="mono">{field.entity}</td>
                  <td className="muted">{field.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Prose text={guide.canonical_bundle.configuration} className="muted" />
      </section>

      <p className="muted mono" style={{ fontSize: "0.76rem" }}>
        integration guide v{guide.guide_version} · digest {guide.guide_digest.slice(0, 12)}
      </p>
    </>
  );
}
