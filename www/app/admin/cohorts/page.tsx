import { redirect } from "next/navigation";

export default function CohortsRedirect() {
  redirect("/admin/analytics");
}
