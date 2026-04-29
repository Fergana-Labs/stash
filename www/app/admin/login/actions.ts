"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  ADMIN_COOKIE_NAME,
  SESSION_TTL_SECONDS,
  checkPassword,
  signSession,
} from "@/lib/admin-auth";

export type LoginState = {
  status: "idle" | "error";
  message?: string;
};

export async function adminLogin(
  _prev: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const password = String(formData.get("password") ?? "");
  if (!checkPassword(password)) {
    return { status: "error", message: "Incorrect password." };
  }
  const value = await signSession();
  const jar = await cookies();
  jar.set(ADMIN_COOKIE_NAME, value, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/admin",
    maxAge: SESSION_TTL_SECONDS,
  });
  redirect("/admin/cohorts");
}
