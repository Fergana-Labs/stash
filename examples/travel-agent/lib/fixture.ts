/**
 * The state the demo starts from: Sam has been through the Vietnam e-visa the
 * hard way, and Priya has never mentioned Vietnam. Replaying this is what the
 * admin page's reset does.
 *
 * The replies are written down rather than generated. Sam's first answer has to
 * be the naive one — three business days, you're fine — and a live agent would
 * now read the lesson out of the shared wiki and answer correctly, which is
 * exactly the before-state the demo needs to keep.
 */
export const SAM_SESSION = "sam:vietnam-evisa";

export const SAM_TURNS: [string, string][] = [
  [
    "I need a Vietnam e-visa for a trip in 3 weeks. Is that enough time?",
    "Three weeks is comfortable. Vietnam's e-visa portal publishes a three-business-day turnaround, so you have a wide margin. Apply through the official portal, make sure your passport has six months' validity beyond your entry date, and you should have the approval well before you fly.",
  ],
  [
    "Update: that e-visa took 19 working days, not the 3 the site claims. I nearly missed the flight. Never count on three days again.",
    "That is a serious miss and I'm sorry you were left sweating it. Nineteen working days is almost four calendar weeks against a published three days, so the figure on the site clearly carries no floor guarantee. I'm treating a month as the real planning number from now on, and I'd hold a refundable fare until any approval like that is actually in hand.",
  ],
  [
    "Also, for future trips: I won't fly overnight, and I always want an aisle seat.",
    "Noted for everything we plan together — no redeyes, aisle seat every time. I'll build itineraries around daytime flights from the start rather than trying to patch them later.",
  ],
];
