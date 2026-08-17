import { ApiDownNotice, NoSnapshotNotice, Portfolio } from "@/components/ui";
import { ApiUnavailable, portfolio } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * The steward view is per-estate: a review queue belongs to one snapshot, so
 * this page picks the estate rather than defaulting to one.
 */
export default async function StewardIndexPage() {
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
      <div className="eyebrow">Steward view</div>
      <h1>Choose an estate to review</h1>
      <p className="lede">
        Each estate keeps its own review queue of low-confidence inferences awaiting a human
        decision, its findings queue ordered by severity, and the draft plays generated from them.
        Open any estate below.
      </p>

      <Portfolio industries={industries} view="steward" />
    </>
  );
}
