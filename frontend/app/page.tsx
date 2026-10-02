import Link from "next/link";
import { ShopDiscovery } from "@/components/shops/ShopDiscovery";
import { MockBadge } from "@/components/ui/MockBadge";

const STARBURST =
  "[clip-path:polygon(50%_0,62%_18%,85%_10%,82%_34%,100%_50%,82%_66%,85%_90%,62%_82%,50%_100%,38%_82%,15%_90%,18%_66%,0_50%,18%_34%,15%_10%,38%_18%)]";

export default function Home() {
  return (
    <main className="mx-auto max-w-[1200px] px-6 py-10">
      <nav className="flex items-center justify-between rounded-full bg-white px-6 py-3 shadow-clay">
        <span className="font-display text-xl">Hinglish Order Desk</span>
        <span className="flex items-center gap-3">
          <Link href="/orders" className="font-display text-base underline">
            My orders
          </Link>
          <MockBadge>DEMO</MockBadge>
        </span>
      </nav>

      <section className="grid items-center gap-12 py-16 md:grid-cols-2">
        <div>
          <p className="eyebrow">AI ordering desk for kirana stores</p>
          <h1 className="mt-3 text-5xl leading-[1.05] md:text-7xl">
            Order the way{" "}
            <span className="relative inline-block">
              <span className="absolute inset-x-0 bottom-1 h-[40%] bg-butter" aria-hidden />
              <span className="relative">you talk.</span>
            </span>
          </h1>
          <p className="mt-6 max-w-lg text-lg text-muted">
            Type, speak or photograph your list in Hinglish, Hindi or Marathi. We match it to the shop&apos;s catalog,
            check stock, ask one short question if needed, and send a clean bill.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <a href="#shops" className="btn-primary">
              → Browse shops
            </a>
            <Link href="/shop/sharma-kirana" className="btn-secondary">
              Open demo shop
            </Link>
            <Link href="/owner/login" className="btn-secondary">
              Shopkeeper login
            </Link>
          </div>
        </div>

        <div className="relative">
          <span
            className={`absolute -right-2 -top-6 z-10 rotate-6 bg-ink p-[3px] ${STARBURST}`}
            aria-hidden
          >
            <span className={`block bg-butter px-5 py-4 font-display text-sm uppercase ${STARBURST}`}>ZAP!</span>
          </span>
          <div className="card bg-lavender">
            <span className="badge bg-white">60 seconds</span>
            <p className="mt-4 rounded-input bg-white p-4 font-medium shadow-clay">
              bhaiya 2 kilo atta, ek Amul butter aur sugar half kilo, tel bhi chahiye
            </p>
            <h3 className="mt-5 text-2xl">Kaunsa tel chahiye?</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="chip">Sunflower 1L ₹155</span>
              <span className="chip">Mustard 1L ₹180</span>
              <span className="chip chip-active">✓ Groundnut 1L ₹190</span>
            </div>
          </div>
        </div>
      </section>

      <ShopDiscovery />
    </main>
  );
}
