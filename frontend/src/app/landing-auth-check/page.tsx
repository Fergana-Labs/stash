import { Suspense } from "react";

import LandingAuthCheckClient from "./LandingAuthCheckClient";

export default function LandingAuthCheckPage() {
  return (
    <Suspense fallback={null}>
      <LandingAuthCheckClient />
    </Suspense>
  );
}
