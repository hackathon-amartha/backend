from fastapi import APIRouter, HTTPException

from app.schemas.item import ItemCreate, ItemUpdate, ItemResponse

router = APIRouter(prefix="/items", tags=["items"])

# In-memory storage for demo
items_db: dict[int, dict] = {}
item_id_counter = 1


@router.get("/", response_model=list[ItemResponse])
async def get_items():
    return [{"id": k, **v} for k, v in items_db.items()]


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"id": item_id, **items_db[item_id]}


@router.post("/", response_model=ItemResponse, status_code=201)
async def create_item(item: ItemCreate):
    global item_id_counter
    items_db[item_id_counter] = item.model_dump()
    response = {"id": item_id_counter, **items_db[item_id_counter]}
    item_id_counter += 1
    return response


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(item_id: int, item: ItemUpdate):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    update_data = item.model_dump(exclude_unset=True)
    items_db[item_id].update(update_data)
    return {"id": item_id, **items_db[item_id]}


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: int):
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    del items_db[item_id]
