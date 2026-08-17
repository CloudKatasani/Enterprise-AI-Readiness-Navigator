import { ApiDownNotice, Pill } from "@/components/ui";
import { ApiUnavailable, connectors } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ConnectorsPage() {
  let catalog;
  try {
    catalog = await connectors();
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  return (
    <>
      <div className="eyebrow">Connectors</div>
      <h1>Permission manifests</h1>
      <p className="lede">
        This is the pack a customer reviews before anything is connected: the exact least-privilege
        grants each connector needs, and the exact statements or API calls it may issue. No connector
        requests row-data access, and CI asserts that every catalogued statement is non-mutating.
      </p>

      <div className="grid cols-2">
        {catalog.map((connector) => (
          <section className="card" key={connector.key}>
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
              <h3 style={{ margin: 0 }}>{connector.display_name}</h3>
              <Pill
                label={connector.live_harvest_available ? "live harvest" : `roadmap ${connector.roadmap_phase}`}
                color={connector.live_harvest_available ? "var(--grade-ready)" : "var(--severity-low)"}
              />
              <Pill label="read-only" color="var(--ocean-600)" />
            </div>
            <p className="muted mono" style={{ margin: "0.5rem 0" }}>
              key {connector.key} · platform {connector.platform}
            </p>

            <h3 style={{ marginTop: "0.9rem" }}>Principal</h3>
            <p className="muted" style={{ marginTop: 0 }}>
              {connector.permission_manifest.principal}
            </p>

            <h3>Grants requested</h3>
            <ul className="muted" style={{ paddingLeft: "1.1rem", margin: "0 0 0.7rem" }}>
              {connector.permission_manifest.grants.map((grant) => (
                <li key={grant.grant} style={{ marginBottom: "0.35rem" }}>
                  <span className="mono">{grant.grant}</span>
                  <div style={{ fontSize: "0.8rem" }}>
                    {grant.scope} — {grant.purpose}
                  </div>
                </li>
              ))}
            </ul>

            {connector.permission_manifest.notes ? (
              <p className="muted" style={{ fontSize: "0.83rem" }}>
                {connector.permission_manifest.notes}
              </p>
            ) : null}

            <div className="muted mono" style={{ fontSize: "0.76rem" }}>
              capabilities: {connector.capabilities.join(", ") || "none declared"}
            </div>
            {connector.query_catalog.length ? (
              <div className="muted mono" style={{ fontSize: "0.76rem" }}>
                SQL catalog: {connector.query_catalog.join(", ")}
              </div>
            ) : null}
            {connector.api_catalog.length ? (
              <div className="muted mono" style={{ fontSize: "0.76rem" }}>
                API catalog: {connector.api_catalog.join(", ")}
              </div>
            ) : null}
            {connector.accepts_canonical_bundle ? (
              <div className="muted" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }}>
                Can assess today from a canonical metadata export (<span className="mono">bundle=</span>
                ) while the live driver lands in {connector.roadmap_phase}.
              </div>
            ) : null}
          </section>
        ))}
      </div>
    </>
  );
}
