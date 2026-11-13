# Licensing FAQ

Decoy (the `decoy-cli` command-line tool; the `decoy-engine` library and the
`decoy-engine-native` companion from their first FSL release onward) is licensed under the
**Functional Source License, Version 1.1, Apache 2.0 Future License** (SPDX: `FSL-1.1-ALv2`).
Engine 0.22.0 and earlier stay Apache-2.0; 0.23.0 and later, including the 0.23.0 the CLI pins today, are FSL-1.1-ALv2. The full terms are in
[`LICENSE.md`](LICENSE.md); this page explains them in plain English. If this page and the
license ever disagree, the license wins.

> TODO(counsel): review this page with the license before the first public release
> (release gate R1-c). "Decoy Labs LLC" is the licensor name pending formation of the LLC.

## The short version

You can use Decoy for anything, including production use at your company, **except** turning
it into a product or service that competes with Decoy. Each release becomes Apache-2.0 open
source two years after it ships.

## Common questions

**Can we use Decoy in production at our company?**
Yes. Masking or generating data for your own systems, CI pipelines, test and staging
environments, and analytics is internal use, which the license explicitly permits. No fee and
no sign-up are needed.

**Can we modify Decoy for our own needs?**
Yes. You can change it, build on it and run your changed version internally.

**Can we use Decoy inside a product we sell?**
Usually yes, as long as masking or synthetic data is not what you are selling. Example: a SaaS
app that masks its own customers' data before sending it to an analytics pipeline is fine. If
your product sells data masking or synthetic data generation to your customers, that is a
Competing Use; contact us for a commercial license.

**Can we sell Decoy, or a product built from it, as our own?**
No. Offering Decoy, or something with the same or substantially similar functionality built
from it, to others as a commercial product or service is a Competing Use. That includes a
hosted or managed masking service.

**Can we fork Decoy, rebrand it, add features and sell it?**
No. Adding features does not change that it is a Competing Use. You also cannot use the Decoy
name or logo for a fork (see [`TRADEMARKS.md`](TRADEMARKS.md)).

**Can a consultancy use Decoy to mask a client's data?**
Yes, when the client is itself using Decoy under these terms. The license explicitly permits
professional services provided to a licensee.

**Can we use Decoy for teaching or research?**
Yes, for non-commercial education and non-commercial research.

**Can we redistribute Decoy?**
Yes, for a permitted purpose, as long as you include the license (or a link to it) and keep the
copyright notices.

**What happens after two years?**
Each release is automatically licensed under Apache-2.0 on the second anniversary of the date
it was released. From then on, that release (and only that release) can be used for any
purpose, including a competing one, under Apache-2.0. Newer releases stay under FSL until their
own two years pass. The trademarks never convert.

**Is there a patent license?**
Yes. The license includes a patent license for permitted uses. It ends if you sue anyone
claiming that Decoy infringes a patent.

**Is Decoy open source?**
Not in the OSI sense today. FSL is source-available: you can read, audit, build and modify all
of the code. Each release becomes open source (Apache-2.0) after two years.

**What about older engine releases that shipped under Apache-2.0?**
They keep the license they shipped with. The change applies to releases from this point on.

**Our legal team cannot approve FSL. What now?**
Contact us about a commercial license. TODO(licensor): add a contact address.

## Why FSL

FSL is a standard license with fixed terms, used by Sentry, Codecov and others, so a legal team
reviews the same text everywhere instead of a custom grant. It lets companies use Decoy freely
while stopping others from reselling it, and it guarantees each release becomes open source.
More at [fsl.software](https://fsl.software).
