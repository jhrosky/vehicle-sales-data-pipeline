with vehicle_sales as (
    select * from {{ ref('int_vehicle_sales') }}
),

dealerships as (
    select * from {{ ref('stg_dealerships') }}
),


joined as (

    select
        -- Vehicle Sales
        vs.vehicle_id,
        vs.make,
        vs.model,
        vs.year,
        vs.vin,
        vs.mileage,
        vs.date_listed,
        vs.sale_id,
        vs.price,
        vs.total_sale,
        vs.date_sold,
		
		--Dealerships
		d.dealership_id,
        d.dealership_name,
        d.region,
		
		round(vs.price - vs.total_sale, 2) as discount,
		datediff('day', vs.date_listed, vs.date_sold) as days_on_lot

    from vehicle_sales vs
    left join dealerships d --left so only vehicle sales have dealerhip data
        on vs.dealership_id = d.dealership_id

)

select * from joined
