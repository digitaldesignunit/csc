import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  return (
    <div className="grid gap-[32px] m-4">
      <Card>
        <CardHeader>
          <CardTitle>Home</CardTitle>
          <CardDescription>
            About the Catalogue of Second Chances
          </CardDescription>
        </CardHeader>
        <CardContent>
            <p>
              <i>Catalogue of Second Chances</i> is an innovative online platform dedicated to promoting sustainability and creativity in design and architecture. It offers an interactive catalog that allows users to explore, store, and access a diverse database of reusable materials and components. This website serves as a bridge between the need for sustainable resources and the creative aspirations of designers and architects, encouraging the practice of recycling and repurposing materials. Through its user-friendly interface, professionals and enthusiasts alike can discover unique items, ranging from construction materials to decorative elements, which can be seamlessly integrated into new projects. The platform not only fosters environmental awareness but also inspires a new wave of design thinking, where every item gets a second chance to shine in a new context.
            </p>
        </CardContent>
      </Card>
    </div>
  );
}
