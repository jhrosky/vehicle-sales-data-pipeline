with source as (

    select * from {{ source('vehicle_sales', 'dealerships') }}

),

renamed as (

	select
		dealership_id,
		name as dealership_name,
		region
	
	from source
	
)

select * from renamed
