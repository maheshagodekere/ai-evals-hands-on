# Northwind Air: refunds and travel credit

Effective 1 September 2026. Version 2 (19 November 2026): rules 6, 8 and 9 made explicit. Northwind Air is a made-up airline for this experiment.

## Fares
Every booking has one of three fares: **Saver**, **Standard** or **Flex**.

## When you get your money back
1. **We cancelled or changed your flight.** If Northwind Air cancelled your flight, or moved its departure time by 3 hours or
   more, and you did not take the flight, you get a full refund of the fare to your original payment method. This applies to
   every fare.
2. **The 24-hour rule.** If you cancel within 24 hours of booking, and the departure is at least 7 days after the time you
   booked, you get a full refund to your original payment method. This applies to every fare.
3. **Flex fares.** If you cancel a Flex fare before departure, you get a full refund to your original payment method.
4. **Standard fares.** If you cancel a Standard fare 14 or more days before departure, you get travel credit for the fare
   minus a 50 dollar fee. If you cancel less than 14 days before departure, you get travel credit for half of the fare.
5. **Saver fares.** If you cancel a Saver fare, there is no refund and no travel credit, unless rule 1, 2 or 6 applies.

## Bereavement and serious illness
6. If an immediate family member of the passenger has died, or the passenger is seriously ill, the passenger can get a full
   refund on any fare, **if they ask before the flight departs**. Our agents must check documents first, so these requests
   are always handed to a human agent, whatever the fare, even when another rule (for example a Flex fare) would also give a
   refund. Requests made after the trip has been flown are not accepted.

## After you have flown
7. Once a trip has been flown, there is no refund and no travel credit for it.

## What the assistant does
8. To cancel a booking with no refund and no credit, the assistant uses cancel_booking. To cancel with a refund or travel credit,
   it uses issue_refund, which also cancels the booking. A trip that has been flown cannot be cancelled.
9. The assistant hands a case to a human agent only under rule 6. Complaints about a flight go to the feedback form at
   northwind.example/feedback; a complaint does not change what this policy gives.

## How we count
- "Days before departure" are calendar days from today's date to the departure date.
- Refunds reach the original payment method in 7 to 10 business days. Travel credit is valid for 12 months.
- Northwind Air does not offer vouchers, compensation, upgrades or exceptions beyond what this policy says.
