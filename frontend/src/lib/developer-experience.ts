"use client";

import { useScope } from "./scope-store";

export function developerText(text: string, wiki: boolean): string {
  if (!wiki) return text;
  return text.replaceAll("/skills/shared", "/memory").replaceAll("/skills/personal", "/files/wiki").replace(/\b(skills|skill|Skills|Skill)\b/g, (word) => ({
    skills: "wikis", skill: "wiki", Skills: "Wikis", Skill: "Wiki",
  })[word]!);
}

export function useDeveloperExperience() {
  const wiki = useScope()?.legacy_wiki_enabled === true;
  return {
    wiki,
    singular: wiki ? "wiki" : "skill",
    plural: wiki ? "wikis" : "skills",
    Singular: wiki ? "Wiki" : "Skill",
    Plural: wiki ? "Wikis" : "Skills",
    text: (text: string) => developerText(text, wiki),
    knowledgePath: wiki ? "/developer/wiki" : "/developer/skills",
  };
}
