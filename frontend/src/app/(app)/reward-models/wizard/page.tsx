import { redirect } from "next/navigation";

/** Wizard conversations are listed with the evals they build. */
export default function WizardIndex() {
  redirect("/reward-models/evals");
}
