type Contact = Pick<
  PointerEvent,
  | "pointerId"
  | "pointerType"
  | "isPrimary"
  | "clientX"
  | "clientY"
  | "timeStamp"
  | "button"
>;
export type TapSide = "left" | "right";
type Tap = { contact: Contact; side: TapSide };

// A pointer contact must start and finish inside the same rail. A cancelled
// drag or second finger discards the whole pair, even if it ends on the rail.
export class DoubleTap {
  private down: Tap | null = null;
  private previous: Tap | null = null;
  reset() {
    this.down = null;
    this.previous = null;
  }
  begin(side: TapSide, event: Contact) {
    if (
      !event.isPrimary ||
      event.button !== 0 ||
      this.down ||
      !["touch", "mouse", "pen"].includes(event.pointerType)
    ) {
      this.reset();
      return false;
    }
    this.down = { side, contact: event };
    return true;
  }
  move(event: Contact) {
    const down = this.down?.contact;
    if (
      down?.pointerId === event.pointerId &&
      Math.hypot(event.clientX - down.clientX, event.clientY - down.clientY) >
        12
    )
      this.reset();
  }
  lost(id: number) {
    if (this.down?.contact.pointerId === id) this.reset();
  }
  end(side: TapSide, event: Contact) {
    const down = this.down;
    if (!down || down.contact.pointerId !== event.pointerId) return false;
    this.move(event);
    if (
      !this.down ||
      down.side !== side ||
      !event.isPrimary ||
      event.button !== 0 ||
      event.timeStamp - down.contact.timeStamp > 280
    ) {
      this.reset();
      return false;
    }
    this.down = null;
    const last = this.previous;
    if (
      last &&
      last.side === side &&
      event.pointerType === last.contact.pointerType &&
      event.timeStamp >= last.contact.timeStamp &&
      event.timeStamp - last.contact.timeStamp <= 380 &&
      Math.hypot(
        event.clientX - last.contact.clientX,
        event.clientY - last.contact.clientY,
      ) <= 30
    ) {
      this.previous = null;
      return true;
    }
    this.previous = { side, contact: event };
    return false;
  }
}
