with vehicles as (

    select * from {{ ref('stg_vehicles') }}

),

sales as (

    select * from {{ ref('stg_sales') }}

),

joined as (

    select
        -- Vehicle
        v.vehicle_id,
        v.make,
        v.model,
        v.year,
        v.vin,
        v.mileage,
        v.dealership_id,
        v.date_listed,

        -- Sales
        s.sale_id,
        s.price,
        s.total_sale,
        s.date_sold

    from vehicles v
    inner join sales s --Inner join becuase only want sold vehicles
        on v.vehicle_id = s.vehicle_id

)

select * from joined
