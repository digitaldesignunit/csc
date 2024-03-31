'use client';

export default async function DataFetch() {
    const getAllComponents = async () => {
        const res = await fetch('https://api.ddu.uber.space/')
        return res.json()
    }

    const comps = await getAllComponents()

    return (
        <div className="grow">
            <h1>Database Components</h1>
            <div>
                <ul>{comps.map( (comp: any) => <li key={comp._id}> {comp._id}, {comp.type}</li>)}</ul>
            </div>
        </div>
    );
}