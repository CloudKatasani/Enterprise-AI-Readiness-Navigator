import { ApiDownNotice, NoSnapshotNotice, Portfolio } from "@/components/ui";
import { ApiUnavailable, portfolio } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * The architect view is per-estate: this page picks which estate to open rather
 * than defaulting to whichever assessment happens to sort first.
 */
export default async function ArchitectIndexPage() {
  let industries;
  try {
    industries = await portfolio();
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }
  if (industries.every((industry) => industry.organisations.length === 0))
    return <NoSnapshotNotice />;

  return (
    <>
      <div className="eyebrow">Architect view</div>
      <h1>Choose an organization to drill into</h1>
      <p className="lede">
        The architect view resolves a score to the evidence behind it: pillar heatmaps by platform
        and by business domain, then every criterion expanded to its check results, confidences and
        failing targets. Open any organization below.
      </p>

      <Portfolio industries={industries} view="architect" />
    </>
  );
}
