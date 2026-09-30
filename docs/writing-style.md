# Writing style

Use this for pages, captions, and other prose on the site.

## Sentences

Write complete sentences. Each sentence has to add a fact. Cut a sentence that only restates the one before it.

A scenario paragraph is the exception. Keep the figures, the disclaimer that they are a scenario and not a forecast, the chart the series comes from, and the judgment those figures support. “Seat sales are plenty” stays in that paragraph.

## The exchange

Say how the exchange works only in ways the API documentation supports. Use the documentation’s names for accounts, actions, and fields. When the passage is the operation itself, keep a documented exception in that passage.

A demand account posts a bid with a service and a price. A supply account grabs the job. The buyer and the provider each sign with a rating from 1 to 5, and the job is completed only when both have signed. The bid stores a currency and a payment method. Those fields are settlement hints for the two sides, unless a configured provider is told to charge now. The exchange does not add a fee to the price.

A supply account grabs an open bid at the price on that bid. Among matching peers, the higher price is preferred.

A party to the job can file a dispute with a reason. The dispute flags the job for admin review. It does not automatically cancel a payment or reverse the ratings.

Prefer those names:

- A demand account posts. A supply account grabs.
- State the rating range, and state that completion requires both signatures.
- Call currency and payment method settlement hints.
- State the charge exception as the docs do: a configured provider is told to charge now.
- Say the exchange does not add a fee to the price.

Do not drift toward “takes the job,” “a note,” “both ratings are in,” “the bid asks to charge now,” or “does not keep a share.”

## Order

State the documented mechanism before any consequence. Fields, the account that acts, and the exception come first. A sentence about what another client can do comes after those facts.

For the infrastructure passage, record the service, the price, and the location type, then who grabs, then the seat-verification gate and that the gate is off, then remote grabs, then both signatures, then the public portfolio, and only then the other client.

Do not open on a label for the exchange, such as “rails” or “a shared API,” and do not lead with the claim that another product keeps its customer.

## Stop when the mechanism is stated

After the documented behavior is on the page, stop. Do not add a sentence that explains it by describing another marketplace’s ads, its slice of the job, or what a client does not have to fund.

A section whose subject is that comparison can name the other company. Merchant of record is that kind of section. Do not attach the comparison to a mechanism paragraph.

The price paragraph is the pattern for stopping. A supply account grabs an open bid at the price on that bid. Among matching peers, the higher price is preferred. The exchange does not add a fee to the price.

## Definitions

A definition says what the thing is and what it is for. It stays short. It does not become the procedure.

A seat is a number and an owner. Seats are not money. A seat is the right to grab jobs on the exchange. Selling that right is how the exchange is paid.

Do not put the phrase, the daily hash, physical versus remote, or the fact that the verification gate is currently off into that definition. Those belong in a passage about the grab operation. “Selling that right is how the exchange is paid” is part of the definition.

## Arguments

Stop at the claim. A zero toll means the price on the bid is the price the parties keep, and a seat is the right to grab jobs at that price.

Say the seat is the right to grab jobs at the price on the bid. Leave the charge-now exception in the passage about payment. Do not say the right is to be the robot. Do not give the seat a term. Do not add that a toll would shrink the seat’s claim on the work, or that the seat would sell for less.

## Where the zero is modeled

Name the pages and the measure, then stop.

The investors page and the business plan both model a take-rate of zero. GMV is jobs cleared.

Leave the retired escrow sketch and the 5% take out of this paragraph. Do not draw the retired 5% take beside the current policy. A side-by-side of who keeps $100 does not help.

## Chart captions

A caption says what one mark on the chart is.

Each bar is new seats that year times $100,000, at network scale 1.0.

When the paragraph above the chart already says the figures are a scenario, not a forecast, and names the chart the series comes from, leave that there. Do not repeat it in the caption. Do not explain a logarithmic axis. Do not say how many times larger the peak bar is.

When the bars are different sets, the caption says what each bar counts, including the set and the source. The app-size caption does that: core download only, most-installed versus most-downloaded, and the Sensor Tower report for each.

## Pictures

A job slip records the work, the price, and the supply account that grabbed the job. The buyer and the provider sign. Payment is not on the slip.

Say that in sentences. Do not caption the slip with a metaphor such as “the whole exchange, on a card.”
