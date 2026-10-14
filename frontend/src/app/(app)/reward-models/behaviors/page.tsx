import { redirect } from "next/navigation";

// Behaviors live on the Traces page now (the Monitors strip); keep old links working.
export default function BehaviorsRedirect() {
  redirect("/reward-models");
}
