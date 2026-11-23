import { useParams } from "react-router-dom";
import { Printer } from "lucide-react";
import { Battlecard } from "@/components/ProviderInsights";
import { Button } from "@/components/ui/primitives";

export default function BattlecardPrint() {
  const { id } = useParams();
  return (
    <div className="mx-auto max-w-[1000px] px-8 py-10">
      <div className="no-print mb-6 flex justify-end"><Button variant="primary" icon={<Printer className="h-4 w-4" />} onClick={() => window.print()}>Afdrukken of opslaan als PDF</Button></div>
      <Battlecard providerId={Number(id)} print />
    </div>
  );
}
